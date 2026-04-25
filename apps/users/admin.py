from allauth.account.models import EmailAddress, EmailConfirmation
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from django.contrib.sites.admin import SiteAdmin
from django.contrib.sites.models import Site
from django.utils.translation import gettext_lazy as _

from .admin_mixins import SuperuserOnlyAdminMixin
from .models import User


@admin.register(User)
class UserAdmin(SuperuserOnlyAdminMixin, DjangoUserAdmin):
    """User management — restricted to SUPERADMIN only."""

    fieldsets = (
        *(DjangoUserAdmin.fieldsets or ()),
        (_("Role"), {"fields": ("role",)}),
        (_("Profile"), {"fields": ("timezone", "preferred_language")}),
    )
    add_fieldsets = (
        *(DjangoUserAdmin.add_fieldsets or ()),
        (_("Role"), {"fields": ("role",)}),
    )
    list_display = (
        "username",
        "email",
        "role",
        "preferred_language",
        "timezone",
    )
    list_filter = (*DjangoUserAdmin.list_filter, "role")


# Group / Site / EmailAddress / EmailConfirmation are all infra concerns —
# only SUPERADMIN should see them. Re-register each with the mixin applied.

for _model, _base_admin in (
    (Group, GroupAdmin),
    (Site, SiteAdmin),
):
    if admin.site.is_registered(_model):
        admin.site.unregister(_model)
    admin.site.register(
        _model,
        type(f"Restricted{_base_admin.__name__}", (SuperuserOnlyAdminMixin, _base_admin), {}),
    )

# allauth's EmailAddress / EmailConfirmation use a plain ModelAdmin; rebuild
# them with the same restriction. They're registered lazily, so guard each.
for _model in (EmailAddress, EmailConfirmation):
    if admin.site.is_registered(_model):
        _existing = type(admin.site._registry[_model])
        admin.site.unregister(_model)
        admin.site.register(
            _model,
            type(
                f"Restricted{_existing.__name__}",
                (SuperuserOnlyAdminMixin, _existing),
                {},
            ),
        )
