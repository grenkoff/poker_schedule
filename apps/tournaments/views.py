"""Public-facing views over Tournament."""

import json

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone

from apps.filters.filters import TournamentFilter
from apps.filters.sort import (
    DEFAULT_SORT,
    SORT_FIELDS,
    apply_sort,
    parse_sort,
    toggle_value,
)

from .columns import PUBLIC_COLUMNS
from .models import Tournament
from .table_state import build_search

PAGE_SIZE = 50


def tournament_list(request: HttpRequest) -> HttpResponse:
    """Upcoming tournaments, filtered and sorted by GET params.

    HTMX calls (identified by the `HX-Request` header) receive only the
    table partial so the filter form above it is preserved — full-page
    loads stay as the SEO-friendly canonical response.
    """
    is_htmx = request.headers.get("HX-Request") == "true"
    # Params that don't count as "user has navigated to a specific view".
    _ignorable = {"e", "_reset"}

    if "_reset" in request.GET and request.user.is_authenticated:
        # Explicit reset: clear saved sort/filter state.
        prefs = request.user.table_pref_json or {}
        prefs["sort"] = None
        prefs["filters"] = ""
        request.user.table_pref_json = prefs
        request.user.save(update_fields=["table_pref_json"])
    elif (
        not is_htmx and request.user.is_authenticated and not (set(request.GET.keys()) - _ignorable)
    ):
        # Clean URL load — restore the user's saved sort/filter state by
        # redirecting to the public-formatted URL.
        target = build_search(request.user.table_pref_json or {}, "public")
        if target:
            return HttpResponseRedirect(request.path + target)

    # Show tournaments while late registration is still open — matches
    # what `prune_expired.js` removes client-side and what `TournamentAdmin`
    # filters on, so users don't see a row vanish before late-reg closes.
    qs = Tournament.objects.filter(
        late_reg_at__gte=timezone.now(),
        verified_by_admin=True,
    ).select_related("room", "room__network", "re_entry", "series")
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(room__name__icontains=q))
    filterset = TournamentFilter(request.GET or None, queryset=qs)
    filtered = apply_sort(filterset.qs, request.GET.get("sort"))

    paginator = Paginator(filtered, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    sort_value = request.GET.get("sort") or DEFAULT_SORT
    current_key, current_desc = parse_sort(sort_value)
    sort_links = {key: toggle_value(sort_value, key) for key in SORT_FIELDS}

    prefs = {}
    if request.user.is_authenticated:
        prefs = request.user.table_pref_json or {}

    context = {
        "filterset": filterset,
        "page_obj": page,
        "tournaments": page.object_list,
        "current_sort_key": current_key,
        "current_sort_desc": current_desc,
        "sort_links": sort_links,
        "has_filters_applied": bool(request.GET.dict()),
        "columns": PUBLIC_COLUMNS,
        "search_query": q,
        "table_prefs_json": json.dumps(prefs),
    }

    template = (
        "tournaments/_tournament_table.html" if is_htmx else "tournaments/tournament_list.html"
    )
    return render(request, template, context)
