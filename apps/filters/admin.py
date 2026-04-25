from django.contrib import admin

from apps.users.admin_mixins import StaffAdminMixin

from .models import SharedFilter


@admin.register(SharedFilter)
class SharedFilterAdmin(StaffAdminMixin, admin.ModelAdmin):
    list_display = ("slug", "name", "created_by", "created_at", "expires_at")
    list_filter = ("created_at",)
    search_fields = ("slug", "name", "created_by__email")
    # `created_by` autocomplete would need view perm on User, which we
    # restrict to SUPERADMIN; readonly is fine — shares are created by
    # the public flow, admins rarely re-attribute one.
    readonly_fields = ("slug", "created_at", "created_by")
