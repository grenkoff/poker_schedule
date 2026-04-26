from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.users.admin_mixins import StaffAdminMixin

from .forms import TournamentAdminForm
from .models import (
    BlindStructure,
    BubbleOption,
    EarlyBirdType,
    Periodicity,
    ReEntryOption,
    Tournament,
)
from .recurrence import regenerate_series


class BlindStructureInline(admin.TabularInline):
    model = BlindStructure
    extra = 1
    min_num = 1
    fields = ("level", "small_blind", "big_blind", "ante")


@admin.register(Tournament)
class TournamentAdmin(StaffAdminMixin, admin.ModelAdmin):
    form = TournamentAdminForm
    list_display = (
        "name",
        "room",
        "game_type",
        "buy_in_total_cents",
        "starting_time",
        "periodicity",
        "submitted_for_review",
        "verified_by_admin",
    )
    list_filter = (
        "room",
        "game_type",
        "re_entry",
        "bubble",
        "periodicity",
        "early_bird",
        "featured_final_table",
        "submitted_for_review",
        "verified_by_admin",
    )
    search_fields = ("name", "room__name")
    date_hierarchy = "starting_time"
    autocomplete_fields = ("room",)
    inlines = (BlindStructureInline,)
    actions = ("submit_for_review", "mark_verified", "unmark_verified")

    fieldsets = (
        (None, {"fields": ("room", "name", "game_type")}),
        (
            _("Buy-in (enter any two; the third is auto-derived)"),
            {"fields": ("buy_in_total", "buy_in_without_rake", "rake")},
        ),
        (
            _("Prize"),
            {"fields": ("guaranteed_dollars", "payout_percent")},
        ),
        (
            _("Stack"),
            {"fields": ("starting_stack", "starting_stack_bb")},
        ),
        (
            _("Time"),
            {
                "fields": (
                    "starting_time",
                    "late_reg_at",
                    "late_reg_level",
                    "blind_interval_minutes",
                    "break_minutes",
                ),
            },
        ),
        (
            _("Tables"),
            {"fields": ("players_per_table", "players_at_final_table")},
        ),
        (
            _("Field"),
            {"fields": ("min_players", "max_players", "re_entry", "bubble")},
        ),
        (
            _("Recurrence"),
            {"fields": ("periodicity", "series_master")},
        ),
        (
            _("Features"),
            {"fields": ("early_bird", "early_bird_type", "featured_final_table")},
        ),
        (
            _("Workflow"),
            {"fields": ("submitted_for_review", "verified_by_admin")},
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = ["series_master"]
        if not request.user.is_superuser:
            readonly.append("verified_by_admin")
        return tuple(readonly)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        instance = form.instance
        if instance.series_master_id is None:
            regenerate_series(instance)

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            actions.pop("mark_verified", None)
            actions.pop("unmark_verified", None)
        return actions

    @admin.action(description=_("Submit selected tournaments for review"))
    def submit_for_review(self, request, queryset):
        updated = queryset.update(submitted_for_review=True)
        self.message_user(request, _("%d tournament(s) submitted for review.") % updated)

    @admin.action(description=_("Mark selected tournaments as verified"))
    def mark_verified(self, request, queryset):
        updated = queryset.update(verified_by_admin=True, submitted_for_review=False)
        self.message_user(request, _("%d tournament(s) marked verified.") % updated)

    @admin.action(description=_("Remove verification from selected tournaments"))
    def unmark_verified(self, request, queryset):
        updated = queryset.update(verified_by_admin=False)
        self.message_user(request, _("%d tournament(s) un-verified.") % updated)


# --- Option lookup tables -------------------------------------------------


class _OptionAdmin(StaffAdminMixin, admin.ModelAdmin):
    list_display = ("label", "name", "sort_order")
    list_editable = ("sort_order",)
    prepopulated_fields = {"name": ("label",)}
    ordering = ("sort_order", "label")


@admin.register(ReEntryOption)
class ReEntryOptionAdmin(_OptionAdmin):
    pass


@admin.register(BubbleOption)
class BubbleOptionAdmin(_OptionAdmin):
    pass


@admin.register(EarlyBirdType)
class EarlyBirdTypeAdmin(_OptionAdmin):
    pass


@admin.register(Periodicity)
class PeriodicityAdmin(_OptionAdmin):
    list_display = ("label", "name", "interval_seconds", "sort_order")
    fields = ("label", "name", "interval_seconds", "sort_order")
