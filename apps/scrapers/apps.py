from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ScrapersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.scrapers"
    verbose_name = _("Scrapers")

    def ready(self) -> None:
        # Import adapter package so every @register decorator runs and
        # populates the registry before any command, task, or view needs it.
        from . import adapters  # noqa: F401
