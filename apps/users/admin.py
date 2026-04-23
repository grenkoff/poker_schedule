from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = (
        *(DjangoUserAdmin.fieldsets or ()),
        (_("Profile"), {"fields": ("timezone", "preferred_language")}),
    )
    list_display = (
        "username",
        "email",
        "preferred_language",
        "timezone",
        "is_staff",
    )
