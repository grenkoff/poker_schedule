"""Column registry for the public tournament list.

Mirrors the columns rendered by `TournamentAdmin.list_display` so the
public page and the admin changelist look identical. Visibility/order
preferences are stored client-side under a separate localStorage key
(see `static/js/public_columns.js`), so user choices on the public page
do not affect admin and vice versa.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.timezone import localtime
from django.utils.translation import gettext_lazy as _

from .models import Tournament


@dataclass(frozen=True)
class Column:
    key: str  # stable identifier, also used as the sort key
    label: object  # gettext_lazy proxy or str
    sort_key: str | None = None  # public sort key (None → not sortable)
    pinned: bool = False  # always first, always visible


PUBLIC_COLUMNS: tuple[Column, ...] = (
    Column("name", _("Name"), sort_key="name", pinned=True),
    Column("room", _("Room"), sort_key="room"),
    Column("game_type", _("Game"), sort_key="game_type"),
    Column("buy_in_total", _("Buy-in with rake, $"), sort_key="buy_in"),
    Column("buy_in_without_rake", _("Buy-in without rake, $"), sort_key="buy_in_without_rake"),
    Column("rake", _("Rake, $"), sort_key="rake"),
    Column("rake_percent", _("Rake %")),
    Column("guaranteed_dollars", _("Guaranteed, $"), sort_key="guaranteed"),
    Column("payout_percent", _("Payout %"), sort_key="payout_percent"),
    Column("starting_stack", _("Starting stack"), sort_key="starting_stack"),
    Column("starting_stack_bb", _("Starting stack, BB"), sort_key="starting_stack_bb"),
    Column("starting_time", _("Starting time"), sort_key="starting_time"),
    Column(
        "late_registration_available",
        _("Late reg available"),
        sort_key="late_registration_available",
    ),
    Column("late_reg_at", _("Late registration closes at"), sort_key="late_reg_at"),
    Column("late_registration_duration", _("Late registration duration")),
    Column("late_reg_level", _("Late reg level"), sort_key="late_reg_level"),
    Column("blind_interval_minutes", _("Blind interval, min"), sort_key="blind_interval"),
    Column("players_per_table", _("Players per table"), sort_key="players_per_table"),
    Column(
        "players_at_final_table",
        _("Players at final table"),
        sort_key="players_at_final_table",
    ),
    Column("min_players", _("Min players"), sort_key="min_players"),
    Column("max_players", _("Max players"), sort_key="max_players"),
    Column("re_entry", _("Re-entry"), sort_key="re_entry"),
    Column("early_bird", _("Early bird"), sort_key="early_bird"),
    Column("featured_final_table", _("Featured FT"), sort_key="featured_final_table"),
    Column("verified_by_admin", _("Verified"), sort_key="verified_by_admin"),
)


def _yesno(value: bool) -> str:
    return "✓" if value else "—"


def render_cell(t: Tournament, key: str) -> str:
    """Render a single cell value matching the admin's display methods."""
    if key == "name":
        return t.name
    if key == "room":
        return t.room.name
    if key == "game_type":
        return t.get_game_type_display()
    if key == "buy_in_total":
        return f"{t.buy_in_total:.2f}"
    if key == "buy_in_without_rake":
        return f"{t.buy_in_without_rake:.2f}"
    if key == "rake":
        return f"{t.rake:.2f}"
    if key == "rake_percent":
        if t.buy_in_total:
            return f"{t.rake / t.buy_in_total * 100:.2f}"
        return "—"
    if key == "guaranteed_dollars":
        return str(t.guaranteed_dollars)
    if key == "payout_percent":
        return str(t.payout_percent)
    if key == "starting_stack":
        return str(t.starting_stack)
    if key == "starting_stack_bb":
        return str(t.starting_stack_bb)
    if key == "starting_time":
        return localtime(t.starting_time).strftime("%d.%m.%Y %H:%M %Z") if t.starting_time else "—"
    if key == "late_registration_available":
        return _yesno(t.late_registration_available)
    if key == "late_reg_at":
        return localtime(t.late_reg_at).strftime("%d.%m.%Y %H:%M %Z") if t.late_reg_at else "—"
    if key == "late_registration_duration":
        if t.late_reg_at and t.starting_time:
            minutes = int((t.late_reg_at - t.starting_time).total_seconds() // 60)
            return f"{minutes} min"
        return "—"
    if key == "late_reg_level":
        return str(t.late_reg_level)
    if key == "blind_interval_minutes":
        return str(t.blind_interval_minutes)
    if key == "players_per_table":
        return str(t.players_per_table)
    if key == "players_at_final_table":
        return str(t.players_at_final_table)
    if key == "min_players":
        return str(t.min_players)
    if key == "max_players":
        return str(t.max_players)
    if key == "re_entry":
        return t.re_entry.label if t.re_entry_id else "—"
    if key == "early_bird":
        return _yesno(t.early_bird)
    if key == "featured_final_table":
        return _yesno(t.featured_final_table)
    if key == "verified_by_admin":
        return _yesno(t.verified_by_admin)
    return ""
