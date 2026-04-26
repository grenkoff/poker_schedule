"""PDF export of the tournament list."""

from __future__ import annotations

from datetime import datetime

from django.http import HttpRequest, HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from apps.filters.filters import TournamentFilter
from apps.filters.sort import apply_sort
from apps.tournaments.models import Tournament


def _render_pdf(request: HttpRequest) -> tuple[bytes, str]:
    qs = Tournament.objects.filter(starting_time__gte=timezone.now()).select_related(
        "room", "room__network"
    )
    filterset = TournamentFilter(request.GET or None, queryset=qs)
    tournaments = apply_sort(filterset.qs, request.GET.get("sort"))

    now = timezone.localtime()
    html = render_to_string(
        "exports/tournament_list.html",
        {
            "tournaments": tournaments,
            "generated_at": now,
            "active_filters": _summarize_filters(filterset),
            "total_count": tournaments.count(),
        },
        request=request,
    )
    pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri()).write_pdf()
    filename = f"poker-schedule-{now:%Y-%m-%d-%H%M}.pdf"
    return pdf_bytes, filename


def export_pdf(request: HttpRequest) -> HttpResponse:
    pdf_bytes, filename = _render_pdf(request)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _summarize_filters(filterset: TournamentFilter) -> list[tuple[str, str]]:
    """Human-readable label/value pairs for the PDF header."""
    items: list[tuple[str, str]] = []
    for name, field in filterset.form.fields.items():
        raw = filterset.form.cleaned_data.get(name) if filterset.form.is_valid() else None
        if not raw:  # None / "" / [] / empty queryset
            continue
        label = str(field.label or name)
        if hasattr(raw, "all"):  # Queryset (ModelMultipleChoiceField)
            display = ", ".join(str(v) for v in raw)
        elif isinstance(raw, list):
            display = ", ".join(str(v) for v in raw)
        elif isinstance(raw, datetime):
            display = raw.strftime("%Y-%m-%d %H:%M %Z")
        else:
            display = str(raw)
        items.append((label, display))
    return items
