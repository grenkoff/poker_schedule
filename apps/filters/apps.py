from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FiltersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.filters"
    verbose_name = _("Filters")
