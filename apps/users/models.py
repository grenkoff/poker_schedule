from django.contrib.auth.models import AbstractUser
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


class User(AbstractUser):
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

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
