"""Single source of truth for tournament-list columns.

Both `TournamentAdmin.list_display` (admin changelist) and the public
tournament-list page (`/`) consume this registry, so a column edit
happens in exactly one place and the two tables can never drift.

Visibility/order preferences are stored client-side; the public and
admin pages use distinct localStorage keys so user choices in one do
not affect the other.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from django.utils.functional import Promise
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.timezone import localtime
from django.utils.translation import gettext_lazy as _

from .models import Tournament


@dataclass(frozen=True)
class Column:
    key: str  # stable identifier; also used as the admin display method name
    label: str | Promise  # column header (gettext_lazy returns a Promise)
    formatter: Callable[[Tournament], str]  # cell renderer
    sort_key: str | None = None  # public URL alias for sorting (e.g. "buy_in")
    db_field: str | None = None  # ORDER BY column (e.g. "buy_in_total")
    pinned: bool = False  # always first, always visible
    admin_only: bool = False  # hide from public list


def _yesno(value: bool) -> str:
    return "✓" if value else "—"


def _fmt_dt(value) -> str | SafeString:
    if not value:
        return "—"
    fallback = localtime(value).strftime("%d.%m.%Y %H:%M %Z")
    return format_html('<time datetime="{}" data-local-dt>{}</time>', value.isoformat(), fallback)


def _fmt_money(value):
    return f"{value:.2f}"


ALL_COLUMNS: tuple[Column, ...] = (
    Column(
        "name",
        _("Name"),
        lambda t: t.name,
        sort_key="name",
        db_field="name",
        pinned=True,
    ),
    Column("room", _("Room"), lambda t: t.room.name, sort_key="room", db_field="room__name"),
    Column(
        "game_type",
        _("Game"),
        lambda t: t.get_game_type_display(),
        sort_key="game_type",
        db_field="game_type",
    ),
    Column(
        "buy_in_total",
        _("Buy-in with rake, $"),
        lambda t: _fmt_money(t.buy_in_total),
        sort_key="buy_in",
        db_field="buy_in_total",
    ),
    Column(
        "buy_in_without_rake",
        _("Buy-in without rake, $"),
        lambda t: _fmt_money(t.buy_in_without_rake),
        sort_key="buy_in_without_rake",
        db_field="buy_in_without_rake",
    ),
    Column(
        "rake",
        _("Rake, $"),
        lambda t: _fmt_money(t.rake),
        sort_key="rake",
        db_field="rake",
    ),
    Column(
        "rake_percent",
        _("Rake %"),
        lambda t: f"{t.rake / t.buy_in_total * 100:.2f}" if t.buy_in_total else "—",
    ),
    Column(
        "guaranteed_dollars",
        _("Guaranteed, $"),
        lambda t: str(t.guaranteed_dollars),
        sort_key="guaranteed",
        db_field="guaranteed_dollars",
    ),
    Column(
        "payout_percent",
        _("Payout %"),
        lambda t: str(t.payout_percent),
        sort_key="payout_percent",
        db_field="payout_percent",
    ),
    Column(
        "starting_stack",
        _("Starting stack"),
        lambda t: str(t.starting_stack),
        sort_key="starting_stack",
        db_field="starting_stack",
    ),
    Column(
        "starting_stack_bb",
        _("Starting stack, BB"),
        lambda t: str(t.starting_stack_bb),
        sort_key="starting_stack_bb",
        db_field="starting_stack_bb",
    ),
    Column(
        "starting_time",
        _("Starting time"),
        lambda t: _fmt_dt(t.starting_time),
        sort_key="starting_time",
        db_field="starting_time",
    ),
    Column(
        "late_registration_available",
        _("Late reg available"),
        lambda t: _yesno(t.late_registration_available),
        sort_key="late_registration_available",
        db_field="late_registration_available",
    ),
    Column(
        "late_reg_at",
        _("Late registration closes at"),
        lambda t: _fmt_dt(t.late_reg_at),
        sort_key="late_reg_at",
        db_field="late_reg_at",
    ),
    Column(
        "late_registration_duration",
        _("Late registration duration"),
        lambda t: (
            f"{int((t.late_reg_at - t.starting_time).total_seconds() // 60)} min"
            if t.late_reg_at and t.starting_time
            else "—"
        ),
    ),
    Column(
        "late_reg_level",
        _("Late reg level"),
        lambda t: str(t.late_reg_level),
        sort_key="late_reg_level",
        db_field="late_reg_level",
    ),
    Column(
        "blind_interval_minutes",
        _("Blind interval, min"),
        lambda t: str(t.blind_interval_minutes),
        sort_key="blind_interval",
        db_field="blind_interval_minutes",
    ),
    Column(
        "players_per_table",
        _("Players per table"),
        lambda t: str(t.players_per_table),
        sort_key="players_per_table",
        db_field="players_per_table",
    ),
    Column(
        "players_at_final_table",
        _("Players at final table"),
        lambda t: str(t.players_at_final_table),
        sort_key="players_at_final_table",
        db_field="players_at_final_table",
    ),
    Column(
        "min_players",
        _("Min players"),
        lambda t: str(t.min_players),
        sort_key="min_players",
        db_field="min_players",
    ),
    Column(
        "max_players",
        _("Max players"),
        lambda t: str(t.max_players),
        sort_key="max_players",
        db_field="max_players",
    ),
    Column(
        "re_entry",
        _("Re-entry"),
        lambda t: t.re_entry.label if t.re_entry_id else "—",
        sort_key="re_entry",
        db_field="re_entry__sort_order",
    ),
    Column(
        "early_bird",
        _("Early bird"),
        lambda t: _yesno(t.early_bird),
        sort_key="early_bird",
        db_field="early_bird",
    ),
    Column(
        "featured_final_table",
        _("Featured final table"),
        lambda t: _yesno(t.featured_final_table),
        sort_key="featured_final_table",
        db_field="featured_final_table",
    ),
    Column(
        "verified_by_admin",
        _("Verified"),
        lambda t: _yesno(t.verified_by_admin),
        sort_key="verified_by_admin",
        db_field="verified_by_admin",
        admin_only=True,
    ),
)


PUBLIC_COLUMNS: tuple[Column, ...] = tuple(c for c in ALL_COLUMNS if not c.admin_only)
