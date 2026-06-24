"""django-import-export resource for bulk Excel (xlsx) round-trip of tournaments.

Foreign keys are matched on the human-readable values editors actually type in
the spreadsheet (room/series names, option slugs) rather than database ids, so a
file can be hand-filled without looking anything up. The derived columns the admin
form normally computes (`buy_in_total`, `is_bounty`, `early_bird`, plus the unexported
`verified_by_admin`) are recomputed on import in `before_save_instance` — see
`TournamentAdminForm` — instead of being trusted from the cell. Columns carry the
admin-form labels (`COLUMN_LABELS`), which also define the accepted import format.
"""

from __future__ import annotations

from decimal import Decimal

from import_export import fields, resources
from import_export.widgets import DateTimeWidget, ForeignKeyWidget

from apps.rooms.models import PokerRoom

from .models import (
    BlindStructureTemplate,
    BountyOption,
    BubbleOption,
    DealMakingOption,
    EarlyBirdType,
    Periodicity,
    ReEntryOption,
    Tournament,
    TournamentSeries,
    blind_signature,
    template_id_for_signature,
)

_DT_FORMAT = "%Y-%m-%d %H:%M"

# Human-readable column headers, matching the tournament admin form labels so the
# spreadsheet reads like the change page rather than like model attributes. These
# double as the import contract: a file must carry exactly these headers (see
# `TournamentResource.before_import`). The two computed booleans get a "(computed)"
# suffix because they'd otherwise collide with their `*_type` siblings' labels.
COLUMN_LABELS = {
    "id": "ID",
    "room": "Room",
    "series": "Tournament series",
    "name": "Name",
    "game_type": "Game type",
    "buy_in_total": "Buy-in (with rake), $",
    "buy_in_without_rake": "Buy-in to prize pool, $",
    "bounty_buyin": "Buy-in to bounty pool, $",
    "rake": "Rake, $",
    "guaranteed_dollars": "Guaranteed prize pool, $",
    "payout_percent": "Payout distribution, %",
    "starting_stack": "Starting chips",
    "starting_stack_bb": "Starting chips, BB",
    "timezone": "Timezone",
    "starting_time": "Starting time",
    "late_registration_available": "Late registration available",
    "late_reg_at": "Late registration closes at",
    "late_reg_level": "Late registration level",
    "blind_interval_minutes": "Blind interval, min",
    "break_minutes": "Break time, min",
    "players_per_table": "Players per table",
    "players_at_final_table": "Players at the final table",
    "min_players": "Min players",
    "max_players": "Max players",
    "re_entry": "Re-entry",
    "bubble": "Bubble",
    "periodicity": "Periodicity",
    "weekdays": "Active weekdays",
    "early_bird": "Early bird (computed)",
    "early_bird_type": "Early bird",
    "featured_final_table": "Featured final table",
    "deal_making": "Deal making",
    "is_bounty": "Bounty (computed)",
    "bounty_type": "Bounty",
    "min_bounty": "Minimum bounty, $",
    "blind_structure": "Blind structure",
}


class SeriesWidget(ForeignKeyWidget):
    """Resolve a `TournamentSeries` by name, scoped to the row's room.

    Series names are only unique per room (`UniqueConstraint(room, slug)`), so we
    need the sibling `room` cell to pick the right one and to reject a series that
    belongs to a different room.
    """

    def __init__(self) -> None:
        super().__init__(TournamentSeries, field="name")

    def clean(self, value, row=None, **kwargs):
        if value in (None, ""):
            return None
        # Rows are keyed by column header (the admin label), not field name.
        room_name = (row or {}).get(COLUMN_LABELS["room"])
        qs = self.model.objects.filter(name=value)
        if room_name:
            qs = qs.filter(room__name=room_name)
        obj = qs.first()
        if obj is None:
            raise ValueError(f"Tournament series '{value}' not found for room '{room_name}'.")
        return obj


class BlindStructureWidget(ForeignKeyWidget):
    """Resolve a `BlindStructureTemplate` by its name for import.

    Used only on the import side: a recognised name lets the import apply that
    template's levels to the tournament (see `TournamentResource`). Export fills
    the column via `dehydrate_blind_structure` instead.
    """

    def __init__(self) -> None:
        super().__init__(BlindStructureTemplate, field="name")

    def clean(self, value, row=None, **kwargs):
        if value in (None, ""):
            return None
        obj = self.model.objects.filter(name=value).first()
        if obj is None:
            raise ValueError(f"Blind structure '{value}' not found.")
        return obj


class TournamentResource(resources.ModelResource):
    room = fields.Field(
        attribute="room",
        column_name="room",
        widget=ForeignKeyWidget(PokerRoom, field="name"),
    )
    series = fields.Field(attribute="series", column_name="series", widget=SeriesWidget())
    re_entry = fields.Field(
        attribute="re_entry",
        column_name="re_entry",
        widget=ForeignKeyWidget(ReEntryOption, field="name"),
    )
    bubble = fields.Field(
        attribute="bubble",
        column_name="bubble",
        widget=ForeignKeyWidget(BubbleOption, field="name"),
    )
    periodicity = fields.Field(
        attribute="periodicity",
        column_name="periodicity",
        widget=ForeignKeyWidget(Periodicity, field="name"),
    )
    bounty_type = fields.Field(
        attribute="bounty_type",
        column_name="bounty_type",
        widget=ForeignKeyWidget(BountyOption, field="name"),
    )
    early_bird_type = fields.Field(
        attribute="early_bird_type",
        column_name="early_bird_type",
        widget=ForeignKeyWidget(EarlyBirdType, field="name"),
    )
    deal_making = fields.Field(
        attribute="deal_making",
        column_name="deal_making",
        widget=ForeignKeyWidget(DealMakingOption, field="name"),
    )
    starting_time = fields.Field(
        attribute="starting_time",
        column_name="starting_time",
        widget=DateTimeWidget(format=_DT_FORMAT),
    )
    late_reg_at = fields.Field(
        attribute="late_reg_at",
        column_name="late_reg_at",
        widget=DateTimeWidget(format=_DT_FORMAT),
    )
    # Not a model field: import sets it to the resolved template (transient attr)
    # and `after_save_instance` copies its levels onto the tournament; export
    # fills the cell from the matching template name via `dehydrate_blind_structure`.
    blind_structure = fields.Field(
        attribute="blind_structure",
        column_name="blind_structure",
        widget=BlindStructureWidget(),
    )

    def __init__(self, user=None, **kwargs):
        super().__init__(**kwargs)
        self._user = user
        self._template_name_cache: dict[int, str] | None = None
        # Relabel every column with its admin-form header (used for both the
        # export header row and import column matching).
        for field_name, label in COLUMN_LABELS.items():
            if field_name in self.fields:
                self.fields[field_name].column_name = label

    def before_import(self, dataset, **kwargs):
        # Reject files that aren't a tournament export: every expected header
        # must be present. Surfaces as a clear error on the import preview page
        # instead of a cryptic per-row failure deep in the mapping.
        super().before_import(dataset, **kwargs)
        required = {self.fields[name].column_name for name in self._meta.fields}
        missing = required - set(dataset.headers or [])
        if missing:
            raise ValueError(
                "This file does not match the tournament export format. "
                "Missing columns: " + ", ".join(sorted(missing)) + ". "
                "Export the tournaments first and fill in that file."
            )

    class Meta:
        model = Tournament
        import_id_fields = ("id",)
        skip_unchanged = True
        report_skipped = True
        # Whitelist + column order. `series_master`, `created_at`, `updated_at`
        # and `verified_by_admin` are intentionally excluded. `buy_in_total`,
        # `is_bounty`, `early_bird` are exported for visibility but recomputed on
        # import; `verified_by_admin` is recomputed too but never shown.
        fields = (
            "id",
            "room",
            "series",
            "name",
            "game_type",
            "buy_in_without_rake",
            "bounty_buyin",
            "rake",
            "buy_in_total",
            "guaranteed_dollars",
            "payout_percent",
            "starting_stack",
            "starting_stack_bb",
            "timezone",
            "starting_time",
            "late_registration_available",
            "late_reg_at",
            "late_reg_level",
            "blind_interval_minutes",
            "break_minutes",
            "players_per_table",
            "players_at_final_table",
            "min_players",
            "max_players",
            "re_entry",
            "bubble",
            "periodicity",
            "weekdays",
            "early_bird",
            "early_bird_type",
            "featured_final_table",
            "deal_making",
            "is_bounty",
            "bounty_type",
            "min_bounty",
            "blind_structure",
        )
        export_order = fields

    def before_save_instance(self, instance, row, **kwargs):
        # Mirror TournamentAdminForm: buy_in_total is the sum of its parts, and
        # the is_bounty / early_bird flags are derived from their optional types.
        instance.buy_in_total = (
            (instance.buy_in_without_rake or Decimal(0))
            + (instance.bounty_buyin or Decimal(0))
            + (instance.rake or Decimal(0))
        )
        instance.early_bird = instance.early_bird_type_id is not None
        instance.is_bounty = instance.bounty_type_id is not None
        # Match TournamentAdmin.save_model: only a superuser's edits are trusted
        # as verified.
        instance.verified_by_admin = bool(self._user and self._user.is_superuser)

    def after_save_instance(self, instance, row, **kwargs):
        # The blind-structure column resolves to a template (transient attr set
        # by the field's widget). Copy its levels onto the now-saved tournament,
        # mirroring TournamentAdmin's "apply template" path. Skipped on dry-run,
        # when the instance may not be persisted.
        if kwargs.get("dry_run"):
            return
        template = getattr(instance, "blind_structure", None)
        if template is not None:
            template.apply_to(instance)

    def dehydrate_blind_structure(self, obj) -> str:
        # Export the name of the template matching the tournament's current
        # blind levels (every saved structure is auto-registered as a template,
        # so this normally resolves). Blank when there are no levels / no match.
        if not obj.pk:
            return ""
        rows = list(obj.blind_levels.all())
        if not rows:
            return ""
        tpl_id = template_id_for_signature(blind_signature(rows))
        if tpl_id is None:
            return ""
        return self._template_names().get(tpl_id, "")

    def _template_names(self) -> dict[int, str]:
        if self._template_name_cache is None:
            self._template_name_cache = dict(
                BlindStructureTemplate.objects.values_list("id", "name")
            )
        return self._template_name_cache
