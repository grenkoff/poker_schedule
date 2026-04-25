from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.core.management.base import CommandError
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
        verification. Maps onto Django's `is_superuser=True`. **Exactly
        one** SUPERADMIN may exist at any time; promoting another user
        auto-demotes the previous one to ADMIN.

    `User.save()` derives `is_staff` and `is_superuser` from this field, so
    the role is the single source of truth for access decisions.
    """

    USER = "user", _("User")
    ADMIN = "admin", _("Admin")
    SUPERADMIN = "superadmin", _("Superadmin")


class UserManager(DjangoUserManager):
    """`createsuperuser` injects `role=SUPERADMIN` and enforces the
    one-superadmin invariant up-front so the CLI fails with a friendly
    `CommandError` instead of an `IntegrityError` from the DB constraint."""

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        if self.filter(role=Role.SUPERADMIN).exists():
            raise CommandError(
                "A SUPERADMIN already exists. Demote them via the admin "
                "(or delete them) before creating another."
            )
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
        constraints = [
            # DB-level safety net for the one-superadmin invariant. The
            # application enforces it in `save()`, but this prevents bad
            # data from sneaking in via raw SQL or `.update()` calls.
            models.UniqueConstraint(
                fields=["role"],
                condition=models.Q(role="superadmin"),
                name="single_superadmin",
            ),
        ]

    def save(self, *args, **kwargs):
        # Role is authoritative — derive Django's is_staff / is_superuser.
        # This means flipping role in the admin instantly grants/revokes
        # admin access on the next request, with no group bookkeeping.
        if self.role == Role.SUPERADMIN:
            self.is_staff = True
            self.is_superuser = True
        elif self.role == Role.ADMIN:
            self.is_staff = True
            self.is_superuser = False
        else:  # USER
            self.is_staff = False
            self.is_superuser = False

        if self.role == Role.SUPERADMIN:
            # Atomic handover: any other SUPERADMIN drops to ADMIN before
            # we land. `.update()` keeps it to a single SQL statement and
            # avoids recursing into save().
            with transaction.atomic():
                others = User.objects.filter(role=Role.SUPERADMIN)
                if self.pk:
                    others = others.exclude(pk=self.pk)
                others.update(role=Role.ADMIN, is_staff=True, is_superuser=False)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Refuse to delete the sole SUPERADMIN — by the invariant, the
        # current SUPERADMIN is always the sole one. Demote first, then
        # delete (the demoted user becomes a normal ADMIN row that's
        # safe to remove).
        if self.role == Role.SUPERADMIN:
            raise PermissionError(
                "Cannot delete the SUPERADMIN. Promote another user to "
                "SUPERADMIN first (which auto-demotes this account), then "
                "delete it."
            )
        return super().delete(*args, **kwargs)
