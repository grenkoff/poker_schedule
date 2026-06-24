"""django-import-export resource for bulk Excel (xlsx) round-trip of tournaments.

Foreign keys are matched on the human-readable values editors actually type in
the spreadsheet (room/series names, option slugs) rather than database ids, so a
file can be hand-filled without looking anything up. The derived columns the admin
form normally computes (`buy_in_total`, `is_bounty`, `early_bird`, `verified_by_admin`)
are recomputed on import in `before_save_instance` — see `TournamentAdminForm` —
instead of being trusted from the cell.
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
        room_name = (row or {}).get("room")
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
