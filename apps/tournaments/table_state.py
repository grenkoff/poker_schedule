"""Translate tournament-table sort/filter state between the public list and
the admin changelist.

The two tables share one stored state (``User.table_pref_json``) so a change
in one place shows up in the other.  Filters are portable as-is — both pages
feed the same ``TournamentFilter`` param names (plus the ``q`` search).  Sort
is **not** portable as a raw query string: the public page uses
``?sort=<sort_key>`` while the admin uses ``?o=<1-based column index>``.  We
therefore store sort semantically (by column ``key`` + direction) and render
each page's own URL from it.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode

from .columns import ALL_COLUMNS

# Params each page owns and that must NOT leak into the portable filter string.
_PUBLIC_META = {"sort", "page", "_reset", "e"}
_ADMIN_META = {"o", "p", "_reset", "e", "all", "t", "_popup"}

# Column key <-> public sort_key (only columns sortable on the public list).
_KEY_BY_SORTKEY = {c.sort_key: c.key for c in ALL_COLUMNS if c.sort_key}
_SORTKEY_BY_KEY = {c.key: c.sort_key for c in ALL_COLUMNS if c.sort_key}

# Column key <-> admin 1-based index into list_display (only sortable columns).
_KEY_BY_INDEX = {i + 1: c.key for i, c in enumerate(ALL_COLUMNS)}
_INDEX_BY_KEY = {c.key: i + 1 for i, c in enumerate(ALL_COLUMNS) if c.db_field}


def parse_params(search: str, mode: str) -> tuple[dict | None, str]:
    """Parse a raw query string into ``(sort, filters)``.

    ``sort`` is ``{"key": <column key>, "desc": bool}`` or ``None``.
    ``filters`` is a portable query string (TournamentFilter params + ``q``),
    with sort/order/meta params and blank values removed.
    """
    items = parse_qsl(search.lstrip("?"), keep_blank_values=False)
    meta = _ADMIN_META if mode == "admin" else _PUBLIC_META

    # Drop meta params and BooleanFilter "no selection" sentinels ("unknown"),
    # which carry no filtering intent and would otherwise clutter the stored
    # state and the restored URL.
    filters = urlencode(
        [(k, v) for k, v in items if k not in meta and v != "unknown"]
    )

    sort = None
    pairs = dict(items)
    if mode == "admin":
        raw = pairs.get("o")
        if raw:
            first = raw.split(".")[0]
            desc = first.startswith("-")
            try:
                idx = abs(int(first))
            except ValueError:
                idx = 0
            key = _KEY_BY_INDEX.get(idx)
            if key:
                sort = {"key": key, "desc": desc}
    else:
        raw = pairs.get("sort")
        if raw:
            desc = raw.startswith("-")
            key = _KEY_BY_SORTKEY.get(raw.lstrip("-"))
            if key:
                sort = {"key": key, "desc": desc}

    return sort, filters


def build_search(prefs: dict | None, mode: str) -> str:
    """Render a query string (with leading ``?``) for ``mode`` from stored
    prefs, or ``""`` when there is nothing to apply."""
    prefs = prefs or {}
    filters = prefs.get("filters") or ""
    sort = prefs.get("sort") or None

    sort_pairs = []
    if sort and sort.get("key"):
        key = sort["key"]
        desc = bool(sort.get("desc"))
        if mode == "admin":
            idx = _INDEX_BY_KEY.get(key)
            if idx:
                sort_pairs.append(("o", f"-{idx}" if desc else str(idx)))
        else:
            sk = _SORTKEY_BY_KEY.get(key)
            if sk:
                sort_pairs.append(("sort", f"-{sk}" if desc else sk))

    sort_qs = urlencode(sort_pairs)
    combined = "&".join(p for p in (sort_qs, filters) if p)
    return ("?" + combined) if combined else ""
