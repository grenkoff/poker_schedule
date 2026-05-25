"""Whitelist-based sort helper.

The `sort` GET param is untrusted input, so we map user-facing keys to
real DB columns and silently fall back to the default on anything
unknown. A leading `-` flips direction.

The whitelist is derived from `apps.tournaments.columns.ALL_COLUMNS`,
keeping the column registry as the single source of truth — no need to
remember to update both places when a sortable column is added.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.tournaments.columns import ALL_COLUMNS
from apps.tournaments.models import Tournament

SORT_FIELDS: dict[str, str] = {
    c.sort_key: c.db_field for c in ALL_COLUMNS if c.sort_key is not None and c.db_field is not None
}

DEFAULT_SORT = "starting_time"


def parse_sort(value: str | None) -> tuple[str, bool]:
    """Return (canonical_key, descending). Invalid input → (DEFAULT_SORT, False)."""
    if not value:
        return DEFAULT_SORT, False
    descending = value.startswith("-")
    key = value.lstrip("-")
    if key not in SORT_FIELDS:
        return DEFAULT_SORT, False
    return key, descending


def apply_sort(qs: QuerySet[Tournament], value: str | None) -> QuerySet[Tournament]:
    key, descending = parse_sort(value)
    column = SORT_FIELDS[key]
    # Cheap-first tiebreaker: when two tournaments share the same primary
    # sort value (e.g. identical starting_time), the lower buy-in comes
    # first. `TournamentAdmin.ordering` mirrors this so the admin and
    # public lists agree on the default order.
    primary = f"-{column}" if descending else column
    return qs.order_by(primary, "buy_in_total")


def toggle_value(current: str | None, target_key: str) -> str:
    """What `?sort=` should become when the user clicks `target_key`.

    - Clicking a different column: sort ascending by it.
    - Clicking the currently-ascending column: switch to descending.
    - Clicking the currently-descending column: go back to the default (asc).
    """
    current_key, current_desc = parse_sort(current)
    if current_key != target_key:
        return target_key
    if not current_desc:
        return f"-{target_key}"
    return target_key
