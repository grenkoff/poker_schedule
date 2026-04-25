from allauth.account.models import EmailAddress, EmailConfirmation
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from django.contrib.sites.admin import SiteAdmin
from django.contrib.sites.models import Site
from django.utils.translation import gettext_lazy as _

from .admin_mixins import SuperuserOnlyAdminMixin
from .models import Role, RoleChangeAudit, User


@admin.register(RoleChangeAudit)
class RoleChangeAuditAdmin(SuperuserOnlyAdminMixin, admin.ModelAdmin):
    """Append-only viewer for the role-change audit log."""

    list_display = (
        "changed_at",
        "user",
        "old_role",
        "new_role",
        "changed_by",
        "source",
        "ip_address",
    )
    list_filter = ("source", "new_role", "old_role")
    search_fields = ("user__username", "user__email", "changed_by__username", "ip_address")
    date_hierarchy = "changed_at"
    readonly_fields = (
        "user",
        "old_role",
        "new_role",
        "changed_by",
        "source",
        "ip_address",
        "user_agent",
        "changed_at",
    )

    def has_add_permission(self, request):
        # Audit rows are written by signals only — never by hand.
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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

    def has_delete_permission(self, request, obj=None):
        # Block delete only when the row is the last SUPERADMIN — promote
        # someone else first, then delete this one.
        if obj is not None and obj.role == Role.SUPERADMIN:
            other_superadmins = User.objects.filter(role=Role.SUPERADMIN).exclude(pk=obj.pk).count()
            if other_superadmins == 0:
                return False
        return super().has_delete_permission(request, obj)


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
