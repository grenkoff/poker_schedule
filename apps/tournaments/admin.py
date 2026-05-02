from django.contrib import admin
from django.http import HttpResponseRedirect
from django.utils.translation import gettext_lazy as _

from apps.users.admin_mixins import StaffAdminMixin

from .forms import BlindStructureInlineForm, TournamentAdminForm
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
    form = BlindStructureInlineForm
    extra = 0
    min_num = 1
    fields = ("level", "small_blind", "big_blind", "ante")


@admin.register(Tournament)
class TournamentAdmin(StaffAdminMixin, admin.ModelAdmin):
    form = TournamentAdminForm

    class Media:
        js = ("admin/js/changelist_columns.js",)
        css = {"all": ("admin/css/changelist_columns.css",)}
    list_display = (
        "name_display",
        "room",
        "game_type",
        "buy_in_dollars",
        "buy_in_without_rake_display",
        "rake_display",
        "rake_percent_display",
        "guaranteed_dollars",
        "payout_percent",
        "starting_stack",
        "starting_stack_bb",
        "starting_time_fmt",
        "late_registration_available",
        "late_reg_at_fmt",
        "late_registration_duration",
        "late_reg_level",
        "blind_interval_minutes",
        "players_per_table",
        "players_at_final_table",
        "min_players",
        "max_players",
        "re_entry",
        "early_bird",
        "featured_final_table",
        "verified_by_admin",
    )
    list_select_related = ("room", "re_entry")
    list_per_page = 100
    list_filter = ()
    search_fields = ("name", "room__name")
    autocomplete_fields = ("room",)
    inlines = (BlindStructureInline,)
    actions = ("mark_verified", "unmark_verified")

    fieldsets = (
        (None, {"fields": ("room", "name", "game_type")}),
        (
            _("Buy-in (with rake = without rake + rake; auto-computed)"),
            {"fields": ("buy_in_without_rake", "rake", "rake_percent", "buy_in_total")},
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
                    "timezone",
                    "starting_time",
                    "late_registration_available",
                    "late_reg_at",
                    "late_registration_duration",
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
    )

    def get_readonly_fields(self, request, obj=None):
        return ("series_master",)

    def has_change_permission(self, request, obj=None) -> bool:
        if not super().has_change_permission(request, obj):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return not obj.verified_by_admin

    def has_delete_permission(self, request, obj=None) -> bool:
        if not super().has_delete_permission(request, obj):
            return False
        if obj is None or request.user.is_superuser:
            return True
        return not obj.verified_by_admin

    def save_model(self, request, obj, form, change):
        obj.verified_by_admin = bool(request.user.is_superuser)
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        instance = form.instance
        if instance.series_master_id is None:
            regenerate_series(instance)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if (
            request.method == "POST"
            and "_unverify" in request.POST
            and request.user.is_superuser
            and object_id
        ):
            Tournament.objects.filter(pk=object_id).update(verified_by_admin=False)
            self.message_user(request, _("Tournament returned for editing."))
            return HttpResponseRedirect(request.path)

        extra_context = extra_context or {}
        obj = self.get_object(request, object_id) if object_id else None
        if obj is not None and obj.verified_by_admin:
            if request.user.is_superuser:
                extra_context["show_unverify_button"] = True
            else:
                extra_context["show_verified_lock_banner"] = True
        return super().change_view(request, object_id, form_url, extra_context)

    @admin.display(description="Buy-in without rake, $", ordering="buy_in_without_rake")
    def buy_in_without_rake_display(self, obj):
        return f"{obj.buy_in_without_rake:.2f}"

    @admin.display(description="Rake, $", ordering="rake")
    def rake_display(self, obj):
        return f"{obj.rake:.2f}"

    @admin.display(description="Rake %")
    def rake_percent_display(self, obj):
        if obj.buy_in_total:
            return f"{obj.rake / obj.buy_in_total * 100:.2f}"
        return "—"

    @admin.display(description="Starting time", ordering="starting_time")
    def starting_time_fmt(self, obj):
        return obj.starting_time.strftime("%d.%m.%Y %H:%M") if obj.starting_time else "—"

    @admin.display(description="Late registration closes at", ordering="late_reg_at")
    def late_reg_at_fmt(self, obj):
        return obj.late_reg_at.strftime("%d.%m.%Y %H:%M") if obj.late_reg_at else "—"

    @admin.display(description="Buy-in with rake, $", ordering="buy_in_total")
    def buy_in_dollars(self, obj):
        return f"{obj.buy_in_total:.2f}"

    @admin.display(description="Name", ordering="name")
    def name_display(self, obj):
        return obj.name

    @admin.display(description=_("Late registration duration"))
    def late_registration_duration(self, obj):
        if obj.late_reg_at and obj.starting_time:
            minutes = int((obj.late_reg_at - obj.starting_time).total_seconds() // 60)
            return f"{minutes} min"
        return "—"

    def get_actions(self, request):
        return {}

    @admin.action(description=_("Mark selected tournaments as verified"))
    def mark_verified(self, request, queryset):
        updated = queryset.update(verified_by_admin=True)
        self.message_user(request, _("%d tournament(s) marked verified.") % updated)

    @admin.action(description=_("Return selected tournaments for editing"))
    def unmark_verified(self, request, queryset):
        updated = queryset.update(verified_by_admin=False)
        self.message_user(request, _("%d tournament(s) returned for editing.") % updated)


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
    list_display = ("label", "name", "interval_seconds", "sort_order")  # type: ignore[assignment]
    fields = ("label", "name", "interval_seconds", "sort_order")
