from django.contrib import admin
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from apps.users.admin_mixins import StaffAdminMixin

from .columns import ALL_COLUMNS, Column
from .forms import (
    BlindStructureInlineForm,
    PeriodicityWidget,
    TournamentAdminForm,
    TournamentSeriesWidget,
)
from .models import (
    BlindStructure,
    BubbleOption,
    DealMakingOption,
    EarlyBirdType,
    Periodicity,
    ReEntryOption,
    Tournament,
    TournamentSeries,
)
from .recurrence import extend_series_to_horizon, regenerate_series


def _wrap_label_words(label) -> str:
    """`Starting time` → `Starting<br>time` so admin th wraps each word.

    The lazy gettext proxy is resolved here at class-load time; project's
    locale catalogs ship empty strings, so admin column headers stay in
    English regardless of the active language — same as today.
    """
    # Safe: input is escape()'d first; only `<br>` is injected.
    return mark_safe(escape(str(label)).replace(" ", "<br>"))  # noqa: S308


def _make_display(column: Column):
    """Wrap a column formatter as an admin display method."""

    def _display(self, obj):
        return column.formatter(obj)

    _display.__name__ = f"col_{column.key}"
    return admin.display(
        description=_wrap_label_words(column.label),
        ordering=column.db_field,
    )(_display)


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
        js = (
            "admin/js/changelist_columns.js",
            "admin/js/series_filter.js",
            "js/localize_times.js",
            "js/sticky_hscroll.js",
            "js/sticky_thead.js",
        )
        css = {"all": ("admin/css/changelist_columns.css",)}

    list_display = tuple(f"col_{c.key}" for c in ALL_COLUMNS)
    list_select_related = ("room", "re_entry", "series")
    # Default sort matches the public list (`apps/filters/sort.py::apply_sort`):
    # starting_time ASC, cheap-first tiebreak. Django's ChangeList still
    # appends `-pk` for stable pagination, which only matters when both
    # primary keys above tie — rare in practice.
    ordering = ("starting_time", "buy_in_total")
    list_per_page = 100
    list_filter = ()
    search_fields = ("name", "room__name")
    inlines = (BlindStructureInline,)
    actions = ("mark_verified", "unmark_verified")

    fieldsets = (
        (None, {"fields": ("room", "series", "name", "game_type")}),
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
            {"fields": ("periodicity", "weekdays", "series_master")},
        ),
        (
            _("Features"),
            {
                "fields": (
                    "early_bird",
                    "early_bird_type",
                    "featured_final_table",
                    "deal_making",
                ),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        return ("series_master",)

    def get_fieldsets(self, request, obj=None):
        # `series_master` only carries information for auto-generated child
        # rows. Hide it on /add/ and on parents that have no master, so the
        # form doesn't show an empty placeholder field nobody can fill.
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None or obj.series_master_id is None:
            fieldsets = tuple(
                (name, {**opts, "fields": tuple(f for f in opts["fields"] if f != "series_master")})
                for name, opts in fieldsets
            )
        return fieldsets

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Custom widgets are wired here (rather than in the form's
        # __init__) so admin's RelatedFieldWidgetWrapper still wraps
        # them afterwards, preserving the +/edit icons and the choices
        # populated by ModelChoiceField.
        if db_field.name == "periodicity":
            kwargs.setdefault("widget", PeriodicityWidget())
        elif db_field.name == "series":
            kwargs.setdefault("widget", TournamentSeriesWidget())
            # Exclude the legacy "Default" series so editors don't pick it.
            # It exists only to satisfy the NOT NULL constraint for rows
            # that existed before per-room series were curated.
            kwargs.setdefault(
                "queryset",
                TournamentSeries.objects.exclude(slug="default").select_related("room"),
            )
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "series" and formfield is not None:
            # Drop the room prefix from each option label — the room is
            # already shown in its own field above. The Room-filter JS
            # uses data-room-id, not the label, so this is purely visual.
            formfield.label_from_instance = lambda obj: obj.name
        if db_field.name == "room" and formfield is not None:
            # Default Select (no autocomplete) — ensure the blank option
            # is present so the user can clear the selection and the
            # series field defaults to disabled on a fresh /add/.
            formfield.empty_label = "---------"
        return formfield

    def get_queryset(self, request):
        self._extend_recurring_series()
        qs = super().get_queryset(request)
        return qs.filter(late_reg_at__gte=timezone.now())

    def _extend_recurring_series(self) -> None:
        masters = (
            Tournament.objects.filter(
                series_master__isnull=True,
                periodicity__interval_seconds__gt=0,
            )
            .select_related("periodicity")
            .prefetch_related("blind_levels")
        )
        for master in masters:
            extend_series_to_horizon(master)

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


# Synthesize one display method per column from the shared registry.
for _col in ALL_COLUMNS:
    setattr(TournamentAdmin, f"col_{_col.key}", _make_display(_col))


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


@admin.register(DealMakingOption)
class DealMakingOptionAdmin(_OptionAdmin):
    pass


@admin.register(Periodicity)
class PeriodicityAdmin(_OptionAdmin):
    list_display = ("label", "name", "interval_seconds", "sort_order")  # type: ignore[assignment]
    fields = ("label", "name", "interval_seconds", "sort_order")


@admin.register(TournamentSeries)
class TournamentSeriesAdmin(StaffAdminMixin, admin.ModelAdmin):
    list_display = ("name", "room", "slug", "sort_order")
    list_filter = ("room",)
    list_editable = ("sort_order",)
    list_select_related = ("room",)
    search_fields = ("name", "room__name")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("room",)
    ordering = ("room__name", "sort_order", "name")
    fields = ("room", "name", "slug", "image", "sort_order")
