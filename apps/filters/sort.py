"""Whitelist-based sort helper.

The `sort` GET param is untrusted input, so we map user-facing keys to
real DB columns and silently fall back to the default on anything
unknown. A leading `-` flips direction.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.tournaments.models import Tournament

# Key → DB column. Keys are short and stable so shareable URLs survive
# internal refactors.
SORT_FIELDS: dict[str, str] = {
    "starting_time": "starting_time",
    "buy_in": "buy_in_total_cents",
    "guaranteed": "guaranteed_dollars",
    "blind_interval": "blind_interval_minutes",
    "room": "room__name",
    "name": "name",
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
    return qs.order_by(f"-{column}" if descending else column)


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
