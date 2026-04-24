"""Shared-filter creation + public view."""

from __future__ import annotations

from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse, QueryDict
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.filters.filters import TournamentFilter
from apps.filters.models import SharedFilter
from apps.filters.sort import (
    DEFAULT_SORT,
    SORT_FIELDS,
    apply_sort,
    parse_sort,
    toggle_value,
)
from apps.tournaments.models import Tournament

PAGE_SIZE = 50


@require_POST
def create_share(request: HttpRequest) -> HttpResponse:
    """Create a SharedFilter from the posted filter state and redirect to it.

    The page embeds every active GET filter as hidden inputs inside the
    share form, so POST carries the whole querystring back intact —
    including multi-valued params.
    """
    # `urlencode` on a QueryDict preserves multi-valued keys (game_type=NLHE
    # &game_type=PLO), which plain dict serialization would drop.
    payload = request.POST.copy()
    # Strip the CSRF token from the stored snapshot.
    payload.pop("csrfmiddlewaretoken", None)
    params_qs = payload.urlencode()

    shared = SharedFilter.objects.create(
        filter_params=params_qs,
        created_by=request.user if request.user.is_authenticated else None,
    )
    return redirect("filters:shared", slug=shared.slug)


def shared_view(request: HttpRequest, slug: str) -> HttpResponse:
    """Read-only tournament list rendered from a stored filter snapshot.

    The recipient can still page and re-sort — those params layer on top
    of the stored filters.
    """
    try:
        shared = SharedFilter.objects.get(slug=slug)
    except SharedFilter.DoesNotExist as exc:
        raise Http404 from exc
    if shared.is_expired():
        raise Http404

    stored = QueryDict(shared.filter_params)
    # Merge: stored filters drive the base result; request.GET only adds
    # sort / pagination on top, never overrides a saved filter value.
    merged = stored.copy()
    for key in ("sort", "page"):
        if value := request.GET.get(key):
            merged[key] = value

    qs = Tournament.objects.filter(start_at__gte=timezone.now()).select_related(
        "room", "room__network"
    )
    filterset = TournamentFilter(merged, queryset=qs)
    filtered = apply_sort(filterset.qs, merged.get("sort"))

    paginator = Paginator(filtered, PAGE_SIZE)
    page = paginator.get_page(merged.get("page"))

    sort_value = merged.get("sort") or DEFAULT_SORT
    current_key, current_desc = parse_sort(sort_value)

    context = {
        "shared": shared,
        "shared_by": shared.created_by.email if shared.created_by else None,
        "filterset": filterset,
        "page_obj": page,
        "tournaments": page.object_list,
        "current_sort_key": current_key,
        "current_sort_desc": current_desc,
        "sort_links": {key: toggle_value(sort_value, key) for key in SORT_FIELDS},
        "has_filters_applied": True,
    }

    is_htmx = request.headers.get("HX-Request") == "true"
    template = "tournaments/_tournament_table.html" if is_htmx else "filters/shared.html"
    return render(request, template, context)
