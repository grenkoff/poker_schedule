from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import BlindStructure, SourceKind, Tournament, TournamentResult


class BlindStructureInline(admin.TabularInline):
    model = BlindStructure
    extra = 0
    fields = ("level", "small_blind", "big_blind", "ante", "duration_minutes")


class TournamentResultInline(admin.TabularInline):
    model = TournamentResult
    extra = 0
    fields = (
        "instance_started_at",
        "entrants",
        "final_table_avg_bb",
        "total_prize_pool_cents",
    )
    readonly_fields = ("created_at",)


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "room",
        "game_type",
        "tournament_format",
        "buy_in_cents",
        "currency",
        "start_at",
        "source_kind",
        "verified_by_admin",
    )
    list_filter = (
        "room",
        "game_type",
        "tournament_format",
        "table_size",
        "source_kind",
        "verified_by_admin",
        "blind_reset_at_final",
    )
    search_fields = ("name", "external_id", "room__name")
    date_hierarchy = "start_at"
    autocomplete_fields = ("room",)
    inlines = (BlindStructureInline, TournamentResultInline)
    actions = ("mark_verified", "unmark_verified")

    fieldsets = (
        (None, {"fields": ("room", "external_id", "name")}),
        (
            _("Structure"),
            {
                "fields": (
                    "game_type",
                    "tournament_format",
                    "table_size",
                    ("buy_in_cents", "rake_cents", "currency"),
                    "starting_stack",
                ),
            },
        ),
        (
            _("Time"),
            {
                "fields": (
                    "start_at",
                    "late_reg_minutes",
                    "blind_level_minutes",
                    "estimated_duration_minutes",
                ),
            },
        ),
        (
            _("Final table"),
            {
                "fields": (
                    "final_table_size",
                    "blind_reset_at_final",
                    "blind_reset_level",
                ),
            },
        ),
        (
            _("Historical metrics"),
            {
                "classes": ("collapse",),
                "fields": ("avg_entrants", "avg_blinds_at_ft"),
            },
        ),
        (
            _("Meta"),
            {
                "fields": (
                    "source_kind",
                    "scraped_at",
                    "verified_by_admin",
                    "raw_payload",
                ),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        base = ("avg_entrants", "avg_blinds_at_ft")
        if obj and obj.source_kind == SourceKind.SCRAPED:
            return (*base, "external_id", "scraped_at", "raw_payload")
        return base

    @admin.action(description=_("Mark selected tournaments as verified"))
    def mark_verified(self, request, queryset):
        updated = queryset.update(verified_by_admin=True)
        self.message_user(request, _("%d tournament(s) marked verified.") % updated)

    @admin.action(description=_("Remove verification from selected tournaments"))
    def unmark_verified(self, request, queryset):
        updated = queryset.update(verified_by_admin=False)
        self.message_user(request, _("%d tournament(s) un-verified.") % updated)


@admin.register(BlindStructure)
class BlindStructureAdmin(admin.ModelAdmin):
    list_display = ("tournament", "level", "small_blind", "big_blind", "ante")
    list_filter = ("tournament__room",)
    search_fields = ("tournament__name",)
    autocomplete_fields = ("tournament",)


@admin.register(TournamentResult)
class TournamentResultAdmin(admin.ModelAdmin):
    list_display = (
        "tournament",
        "instance_started_at",
        "entrants",
        "final_table_avg_bb",
    )
    list_filter = ("tournament__room",)
    search_fields = ("tournament__name",)
    date_hierarchy = "instance_started_at"
    autocomplete_fields = ("tournament",)
    readonly_fields = ("created_at",)
