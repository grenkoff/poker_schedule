from django.contrib import admin

from .models import Network, PokerRoom


@admin.register(Network)
class NetworkAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "website")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(PokerRoom)
class PokerRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "network", "slug", "is_active", "website")
    list_filter = ("network", "is_active")
    search_fields = ("name", "slug")
    list_editable = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("network",)
