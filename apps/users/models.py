from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from django.db import models
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
        one SUPERADMIN exists for the lifetime of the project**: once
        assigned, the role cannot be transferred, taken away, or deleted.
        The first `manage.py createsuperuser` claims it and that's it.

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
                "A SUPERADMIN already exists. The role is permanent — "
                "only one ever exists for the lifetime of the project."
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

        self._enforce_superadmin_invariants()
        super().save(*args, **kwargs)

    def _enforce_superadmin_invariants(self) -> None:
        """SUPERADMIN is permanent and singular.

        - It cannot be moved off the user who currently holds it.
        - It cannot be assigned to anyone else once held.

        Raised as ValidationError so admin form validation surfaces it
        cleanly; programmatic callers get the same exception.
        """
        prior_role: str | None = None
        if self.pk:
            prior = User.objects.filter(pk=self.pk).only("role").first()
            prior_role = prior.role if prior else None

        # The current SUPERADMIN cannot demote themselves.
        if prior_role == Role.SUPERADMIN and self.role != Role.SUPERADMIN:
            raise ValidationError(
                {"role": _("The SUPERADMIN role is permanent and cannot be removed.")}
            )

        # No-one else can be promoted to SUPERADMIN once one exists.
        if self.role == Role.SUPERADMIN and prior_role != Role.SUPERADMIN:
            existing = User.objects.filter(role=Role.SUPERADMIN)
            if self.pk:
                existing = existing.exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError(
                    {"role": _("A SUPERADMIN already exists. The role cannot be transferred.")}
                )

    def delete(self, *args, **kwargs):
        # The SUPERADMIN is permanent — no demote, no delete.
        if self.role == Role.SUPERADMIN:
            raise PermissionError(
                "The SUPERADMIN account cannot be deleted — the role is permanent."
            )
        return super().delete(*args, **kwargs)
