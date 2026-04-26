"""Public-facing views over Tournament."""

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
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

from .models import Tournament

PAGE_SIZE = 50


def tournament_list(request: HttpRequest) -> HttpResponse:
    """Upcoming tournaments, filtered and sorted by GET params.

    HTMX calls (identified by the `HX-Request` header) receive only the
    table partial so the filter form above it is preserved — full-page
    loads stay as the SEO-friendly canonical response.
    """
    qs = Tournament.objects.filter(starting_time__gte=timezone.now()).select_related(
        "room", "room__network"
    )
    filterset = TournamentFilter(request.GET or None, queryset=qs)
    filtered = apply_sort(filterset.qs, request.GET.get("sort"))

    paginator = Paginator(filtered, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    sort_value = request.GET.get("sort") or DEFAULT_SORT
    current_key, current_desc = parse_sort(sort_value)
    sort_links = {key: toggle_value(sort_value, key) for key in SORT_FIELDS}

    context = {
        "filterset": filterset,
        "page_obj": page,
        "tournaments": page.object_list,
        "current_sort_key": current_key,
        "current_sort_desc": current_desc,
        "sort_links": sort_links,
        "has_filters_applied": bool(request.GET.dict()),
    }

    is_htmx = request.headers.get("HX-Request") == "true"
    template = (
        "tournaments/_tournament_table.html" if is_htmx else "tournaments/tournament_list.html"
    )
    return render(request, template, context)
