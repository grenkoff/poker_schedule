"""Permission mixins for ModelAdmin classes — keep role gating in one place.

Django's default ModelAdmin checks per-model permissions on the user. Our
ADMIN role gives `is_staff=True` but assigns no individual permissions,
so without these mixins ADMIN logs into /admin/ and sees nothing. The
mixins map our two non-trivial roles onto the admin permission API:

- `StaffAdminMixin` — visible / editable by any staff user (ADMIN + SUPERADMIN).
- `SuperuserOnlyAdminMixin` — visible / editable only by SUPERADMIN.
"""

from __future__ import annotations


class StaffAdminMixin:
    """Allow any `is_staff` user (ADMIN or SUPERADMIN) full ModelAdmin access."""

    def has_module_permission(self, request) -> bool:
        return bool(request.user and request.user.is_staff)

    def has_view_permission(self, request, obj=None) -> bool:
        return bool(request.user and request.user.is_staff)

    def has_add_permission(self, request) -> bool:
        return bool(request.user and request.user.is_staff)

    def has_change_permission(self, request, obj=None) -> bool:
        return bool(request.user and request.user.is_staff)

    def has_delete_permission(self, request, obj=None) -> bool:
        return bool(request.user and request.user.is_staff)


class SuperuserOnlyAdminMixin:
    """Restrict the wrapped ModelAdmin to SUPERADMIN-only access."""

    def has_module_permission(self, request) -> bool:
        return bool(request.user and request.user.is_superuser)

    def has_view_permission(self, request, obj=None) -> bool:
        return bool(request.user and request.user.is_superuser)

    def has_add_permission(self, request) -> bool:
        return bool(request.user and request.user.is_superuser)

    def has_change_permission(self, request, obj=None) -> bool:
        return bool(request.user and request.user.is_superuser)

    def has_delete_permission(self, request, obj=None) -> bool:
        return bool(request.user and request.user.is_superuser)
