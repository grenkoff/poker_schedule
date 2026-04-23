"""Public-facing views over Tournament."""

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from .models import Tournament

PAGE_SIZE = 50


def tournament_list(request: HttpRequest) -> HttpResponse:
    """Upcoming tournaments, ordered by start time.

    Filters (Phase 3) will layer on top of this queryset via request.GET.
    """
    qs = (
        Tournament.objects.filter(start_at__gte=timezone.now())
        .select_related("room", "room__network")
        .order_by("start_at")
    )
    paginator = Paginator(qs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "tournaments/tournament_list.html",
        {
            "page_obj": page,
            "tournaments": page.object_list,
        },
    )
