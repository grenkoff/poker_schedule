from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

# Subset of supported language codes — kept in sync with
# settings.LANGUAGES. Stored on the user so we can honour their preference
# in emails and PDFs, not only in the interactive UI.
LANGUAGE_CHOICES = [
    ("en", "English"),
    ("ru", "Русский"),
    ("es", "Español"),
    ("pt-br", "Português (Brasil)"),
    ("de", "Deutsch"),
    ("fr", "Français"),
    ("zh-hans", "简体中文"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("uk", "Українська"),
]


class Role(models.TextChoices):
    """Three-tier access model.

    USER — regular player; can view, filter, share, download.
    ADMIN — content editor; can create/edit tournaments and rooms, can
        submit edits for verification by SUPERADMIN. Cannot manage users
        or verify their own work.
    SUPERADMIN — full access including user management and final
        verification. Maps onto Django's `is_superuser=True`. Multiple
        SUPERADMINs may exist (think GitHub org owners or Atlassian site
        administrators), but the system always keeps **at least one** —
        the last one cannot demote or delete themselves, and a delete
        that would leave zero SUPERADMINs is rejected.

    `User.save()` derives `is_staff` and `is_superuser` from this field, so
    the role is the single source of truth for access decisions.
    """

    USER = "user", _("User")
    ADMIN = "admin", _("Admin")
    SUPERADMIN = "superadmin", _("Superadmin")


class UserManager(DjangoUserManager):
    """`createsuperuser` injects `role=SUPERADMIN` so the resulting account
    matches the role-driven flag-sync in `User.save()`."""

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.SUPERADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    role = models.CharField(
        _("role"),
        max_length=16,
        choices=Role.choices,
        default=Role.USER,
        help_text=_("Drives is_staff and is_superuser via User.save()."),
    )
    timezone = models.CharField(
        _("timezone"),
        max_length=64,
        default="UTC",
        help_text=_("IANA timezone name, e.g. Europe/Moscow."),
    )
    preferred_language = models.CharField(
        _("preferred language"),
        max_length=10,
        choices=LANGUAGE_CHOICES,
        default="en",
    )

    objects = UserManager()  # type: ignore[misc]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def save(self, *args, **kwargs):
        # Role is authoritative — derive Django's is_staff / is_superuser.
        if self.role == Role.SUPERADMIN:
            self.is_staff = True
            self.is_superuser = True
        elif self.role == Role.ADMIN:
            self.is_staff = True
            self.is_superuser = False
        else:  # USER
            self.is_staff = False
            self.is_superuser = False

        self._enforce_min_one_superadmin_on_demote()
        super().save(*args, **kwargs)

    def _enforce_min_one_superadmin_on_demote(self) -> None:
        """When demoting a SUPERADMIN, ensure at least one will remain.

        Promotion to SUPERADMIN is unrestricted — any number is fine.
        """
        if not self.pk:
            return  # new row; cannot be demoting an existing SUPERADMIN
        prior = User.objects.filter(pk=self.pk).only("role").first()
        if prior is None or prior.role != Role.SUPERADMIN:
            return
        if self.role == Role.SUPERADMIN:
            return  # not changing
        # Use SELECT FOR UPDATE so two concurrent demotions don't both pass.
        with transaction.atomic():
            others = (
                User.objects.select_for_update()
                .filter(role=Role.SUPERADMIN)
                .exclude(pk=self.pk)
                .count()
            )
        if others == 0:
            raise ValidationError(
                {
                    "role": _(
                        "Cannot demote the last SUPERADMIN. Promote another "
                        "user to SUPERADMIN first."
                    )
                }
            )

    def delete(self, *args, **kwargs):
        if self.role == Role.SUPERADMIN:
            with transaction.atomic():
                others = (
                    User.objects.select_for_update()
                    .filter(role=Role.SUPERADMIN)
                    .exclude(pk=self.pk)
                    .count()
                )
            if others == 0:
                raise PermissionError(
                    "Cannot delete the last SUPERADMIN. Promote another user to SUPERADMIN first."
                )
        return super().delete(*args, **kwargs)


class AuditSource(models.TextChoices):
    ADMIN = "admin", _("Django admin")
    CLI = "cli", _("Management command")
    SIGNUP = "signup", _("Signup flow")
    OTHER = "other", _("Other")


class RoleChangeAudit(models.Model):
    """Append-only log of every change to `User.role`.

    Created from a `post_save` signal on `User`; the request context (who,
    from which IP) is supplied by `apps.users.audit_context.AuditContextMiddleware`.
    Records are kept indefinitely — there's no auto-cleanup yet.
    """

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="role_audits",
        verbose_name=_("user"),
    )
    old_role = models.CharField(_("old role"), max_length=16, blank=True)
    new_role = models.CharField(_("new role"), max_length=16)
    changed_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_changes_made",
        verbose_name=_("changed by"),
    )
    source = models.CharField(
        _("source"),
        max_length=16,
        choices=AuditSource.choices,
        default=AuditSource.OTHER,
    )
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.CharField(_("user agent"), max_length=512, blank=True)
    changed_at = models.DateTimeField(_("changed at"), auto_now_add=True)

    class Meta:
        verbose_name = _("role change")
        verbose_name_plural = _("role changes")
        ordering = ("-changed_at",)
        indexes = [
            models.Index(fields=["-changed_at"]),
            models.Index(fields=["user", "-changed_at"]),
        ]

    def __str__(self) -> str:
        old = self.old_role or "(new)"
        return f"{self.user.username}: {old} -> {self.new_role} @ {self.changed_at:%Y-%m-%d %H:%M}"
