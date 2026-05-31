from django.contrib import admin, messages
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.users.admin_mixins import StaffAdminMixin

from .columns import _fmt_decimal, _with_unit

from .forms import (
    BlindLevelTemplateInlineForm,
    BlindStructureInlineForm,
    PeriodicityWidget,
    TournamentAdminForm,
    TournamentSeriesWidget,
)
from .models import (
    BlindLevelTemplate,
    BlindStructure,
    BlindStructureTemplate,
    BubbleOption,
    DealMakingOption,
    EarlyBirdType,
    Periodicity,
    ReEntryOption,
    Tournament,
    TournamentSeries,
    auto_template_name,
    blind_signature,
    template_id_for_signature,
)
from .recurrence import extend_series_to_horizon, regenerate_series


class BlindStructureInline(admin.TabularInline):
    model = BlindStructure
    form = BlindStructureInlineForm
    extra = 0
    min_num = 1
    fields = ("level", "small_blind", "big_blind", "ante")


class BlindLevelTemplateInline(admin.TabularInline):
    model = BlindLevelTemplate
    form = BlindLevelTemplateInlineForm
    extra = 0
    min_num = 1
    fields = ("level", "small_blind", "big_blind", "ante")


@admin.register(BlindStructureTemplate)
class BlindStructureTemplateAdmin(StaffAdminMixin, admin.ModelAdmin):
    list_display = ("name", "level_count", "created_at")
    search_fields = ("name",)
    ordering = ("name",)
    # `name` is auto-derived from levels in save_related; no other model
    # field belongs on the form, so exclude it explicitly. `fields = ()`
    # would be falsy and silently fall back to "all model fields".
    exclude = ("name",)
    inlines = (BlindLevelTemplateInline,)

    class Media:
        # Reuse the BlindStructure inline's autonumber + derive-small-blind
        # JS for the template editor. The first-row big_blind derivation
        # falls back to no-op (no starting_stack input on the page) and
        # leaves the editor free to type any number.
        # integer_thousand_seps must load first — see TournamentAdminForm.Media.
        js = (
            "admin/js/integer_thousand_seps.js",
            "admin/js/blind_levels_autonumber.js",
        )
        css = {"all": ("admin/css/blind_inline.css",)}

    @admin.display(description=_("levels"))
    def level_count(self, obj) -> int:
        return obj.levels.count()

    def save_model(self, request, obj, form, change):
        # `name` is unique + non-null. We auto-derive it from the levels
        # in save_related (which runs after the inline is persisted), so
        # we need a temporary unique value here just to satisfy the DB
        # on the initial insert. save_related rewrites it immediately.
        if not obj.name:
            import uuid

            obj.name = f"new-{uuid.uuid4().hex[:8]}"
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        instance = form.instance
        rows = list(instance.levels.all())
        if not rows:
            return
        canonical = auto_template_name(rows)
        if instance.name == canonical:
            return
        # Another template might already own this canonical name (it
        # would be a content-equivalent duplicate). Fall through to the
        # unique-constraint error — the editor can resolve manually.
        try:
            instance.name = canonical
            instance.save(update_fields=["name", "updated_at"])
        except IntegrityError:
            self.message_user(
                request,
                _(
                    "An identical blind structure already exists. "
                    "Delete this duplicate and use the existing template instead."
                ),
                level=messages.WARNING,
            )


@admin.register(Tournament)
class TournamentAdmin(StaffAdminMixin, admin.ModelAdmin):
    form = TournamentAdminForm

    class Media:
        js = (
            # Change-form helper: filters the series dropdown by selected room.
            "admin/js/series_filter.js",
            # Changelist: typeahead dropdown on the search box.
            "admin/js/tournament_autocomplete.js",
        )
        css = {"all": ("admin/css/tournament_autocomplete.css",)}

    # Plain Django changelist: a few key columns, alphabetical by name.
    list_display = (
        "name",
        "room",
        "series_name",
        "game_type",
        "buy_in_display",
        "starting_time",
        "verified_by_admin",
    )
    list_select_related = ("room", "series")
    ordering = ("name",)

    @admin.display(description=_("Tournament series"), ordering="series__name")
    def series_name(self, obj):
        # Drop the "Room — " prefix from TournamentSeries.__str__; the Room
        # column already shows it.
        return obj.series.name if obj.series_id else "—"

    @admin.display(description=_("Buy-in (with rake), $"), ordering="buy_in_total")
    def buy_in_display(self, obj):
        # Same formatting as the public list: "$1", "$1.88" (no trailing .00).
        return _with_unit(_fmt_decimal(obj.buy_in_total), prefix="$")
    list_per_page = 100
    search_fields = ("name", "room__name")
    inlines = (BlindStructureInline,)
    actions = ("mark_verified", "unmark_verified")

    def get_urls(self):
        # Custom URLs must precede the catch-all `<object_id>/` admin route.
        return [
            path(
                "autocomplete-json/",
                self.admin_site.admin_view(self.autocomplete_json),
                name="tournaments_tournament_autocomplete_json",
            ),
        ] + super().get_urls()

    def autocomplete_json(self, request):
        """Typeahead results for the changelist search box.

        Scoped to the same rows the changelist shows (series masters + open
        one-offs), so every suggestion opens an editable change page.
        """
        q = (request.GET.get("q") or "").strip()
        results = []
        if q:
            qs = (
                Tournament.objects.filter(series_master__isnull=True)
                .filter(
                    Q(periodicity__interval_seconds__gt=0)
                    | Q(late_reg_at__gte=timezone.now())
                )
                .filter(Q(name__icontains=q) | Q(room__name__icontains=q))
                .select_related("room")
                .order_by("name")[:10]
            )
            for t in qs:
                results.append(
                    {
                        "name": t.name,
                        "room": t.room.name if t.room_id else "",
                        "url": reverse("admin:tournaments_tournament_change", args=[t.pk]),
                    }
                )
        return JsonResponse({"results": results})

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
                    "early_bird_type",
                    "featured_final_table",
                    "deal_making",
                ),
            },
        ),
        (
            _("Blind structure template"),
            {
                "fields": ("apply_template",),
                "description": _(
                    "Optionally load an existing template into the BLIND LEVELS "
                    "table below. Any new structure not already in the library "
                    "is saved as a new template automatically on save."
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
        from django.db.models import Q

        # Show only "source" rows: recurring-series MASTERS (any date, so the
        # series stays editable) and one-off tournaments with open late-reg.
        # Auto-generated series children (`series_master` set) are excluded so
        # the list isn't flooded with one row per occurrence — they're managed
        # via their master and still appear in full on the public page.
        return qs.filter(series_master__isnull=True).filter(
            Q(periodicity__interval_seconds__gt=0) | Q(late_reg_at__gte=timezone.now())
        )

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

        # Ordering matters:
        #   1. Apply template (overwrites the inline rows the editor
        #      submitted) — so the editor's pick wins over typed rows.
        #   2. Snapshot as a new template (captures the FINAL row set,
        #      so "load X → tweak → save as Y" works in one submission).
        #   3. Regenerate series children — so masters propagate the
        #      template-derived rows down to children without needing
        #      changes in `recurrence.py`.
        apply_template = form.cleaned_data.get("apply_template")
        if apply_template is not None:
            current_sig = blind_signature(instance.blind_levels.all())
            template_sig = blind_signature(apply_template.levels.all())
            if current_sig != template_sig:
                apply_template.apply_to(instance)

        # Auto-save the structure as a template whenever it's new. The
        # dedup check inside `_save_as_template` short-circuits when
        # the inline rows already match an existing template, so this
        # is a no-op for unchanged tournaments and tournaments that
        # loaded an existing template.
        if list(instance.blind_levels.all()):
            self._save_as_template(request, instance)

        if instance.series_master_id is None:
            regenerate_series(instance)

    def _save_as_template(self, request, instance) -> None:
        """Auto-save the tournament's blind structure as a template.

        Dedup first: if an identical structure already exists no new
        template is created. Otherwise a fresh template is created
        with a content-derived auto-name.
        """
        sig = blind_signature(instance.blind_levels.all())
        existing_id = template_id_for_signature(sig)
        if existing_id is not None:
            existing = BlindStructureTemplate.objects.get(pk=existing_id)
            self.message_user(
                request,
                _("Blind structure matches existing template '%(n)s' — no new template created.")
                % {"n": existing.name},
                level=messages.INFO,
            )
            return
        name = self._auto_template_name(instance)
        try:
            BlindStructureTemplate.create_from_tournament(instance, name=name)
            self.message_user(
                request,
                _("Saved blind structure as template '%(n)s'.") % {"n": name},
            )
        except IntegrityError:
            self.message_user(
                request,
                _("Template name '%(n)s' already exists; not saved.") % {"n": name},
                level=messages.WARNING,
            )

    @staticmethod
    def _auto_template_name(instance) -> str:
        """Content-based name from the tournament's blind_levels.

        Returns e.g. '1-100(12)_5-1,600(150) [a1b2c3]'. The hash slice
        is always present; equal signatures produce equal names, which
        the dedup path in `_save_as_template` will collapse before any
        new template is created.
        """
        rows = list(instance.blind_levels.all())
        if not rows:
            return f"Like {instance.name}"[:120]
        return auto_template_name(rows)[:120]

    # --- "Save and add same" ---------------------------------------------

    # Fields we never carry from the source tournament when cloning:
    # `id` so the clone gets a fresh PK; `series_master` so the clone
    # stands on its own (even if the source was a series child);
    # `verified_by_admin` so the clone goes through verification again.
    _CLONE_SKIP_FIELDS = frozenset({"id", "series_master", "verified_by_admin"})

    @transaction.atomic
    def _clone_tournament(self, source: Tournament) -> Tournament:
        data = {
            field.name: getattr(source, field.name)
            for field in Tournament._meta.concrete_fields
            if field.name not in self._CLONE_SKIP_FIELDS
        }
        data["verified_by_admin"] = False
        clone = Tournament.objects.create(**data)
        for level in source.blind_levels.all():
            BlindStructure.objects.create(
                tournament=clone,
                level=level.level,
                small_blind=level.small_blind,
                big_blind=level.big_blind,
                ante=level.ante,
            )
        # Mirror what `save_related` does for normal save paths: if the
        # clone is a (new) recurring master, generate its children now.
        if clone.periodicity and clone.periodicity.interval_seconds > 0:
            regenerate_series(clone)
        return clone

    def _addsame_redirect(self, request, source):
        clone = self._clone_tournament(source)
        self.message_user(
            request,
            _("Cloned from “%(name)s” — edit the new tournament below.") % {"name": source.name},
        )
        return HttpResponseRedirect(reverse("admin:tournaments_tournament_change", args=[clone.pk]))

    def response_add(self, request, obj, post_url_continue=None):
        if "_addsame" in request.POST:
            return self._addsame_redirect(request, obj)
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if "_addsame" in request.POST:
            return self._addsame_redirect(request, obj)
        return super().response_change(request, obj)

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
