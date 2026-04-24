from django.contrib import admin

from .models import SharedFilter


@admin.register(SharedFilter)
class SharedFilterAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "created_by", "created_at", "expires_at")
    list_filter = ("created_at",)
    search_fields = ("slug", "name", "created_by__email")
    readonly_fields = ("slug", "created_at")
    autocomplete_fields = ("created_by",)
