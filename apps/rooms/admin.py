from django.contrib import admin

from apps.users.admin_mixins import StaffAdminMixin

from .models import Network, PokerRoom


@admin.register(Network)
class NetworkAdmin(StaffAdminMixin, admin.ModelAdmin):
    list_display = ("name", "slug", "website")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(PokerRoom)
class PokerRoomAdmin(StaffAdminMixin, admin.ModelAdmin):
    list_display = ("name", "network", "slug", "horizon_days", "is_active", "website")
    list_filter = ("network", "is_active")
    search_fields = ("name", "slug")
    list_editable = ("is_active", "horizon_days")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("network",)
    fields = ("name", "slug", "network", "website", "image", "horizon_days", "is_active")
