from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
    verbose_name = _("Users")

    def ready(self) -> None:
        # Import signal handlers so the role-change audit log starts
        # writing as soon as Django is up.
        from . import signals  # noqa: F401
