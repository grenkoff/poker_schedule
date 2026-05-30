"""Profile management views."""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.tournaments.columns import ALL_COLUMNS
from apps.tournaments.table_state import parse_params

from .forms import TIMEZONE_SUGGESTIONS, ProfileForm


@login_required
def profile(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Profile updated."))
            return redirect(reverse("users:profile"))
    else:
        form = ProfileForm(instance=request.user)

    return render(
        request,
        "users/profile.html",
        {"form": form, "timezone_suggestions": TIMEZONE_SUGGESTIONS},
    )


@login_required
@require_POST
def save_table_prefs(request: HttpRequest) -> JsonResponse:
    """POST /profile/table-prefs/ — persist column order/visibility plus the
    page's sort/filter state.

    The client sends ``{columns, params, mode}`` where ``params`` is the page's
    raw query string and ``mode`` is ``"public"`` or ``"admin"``. Sort/filter
    state is stored semantically (by column key) so it can be replayed on the
    other table, whose sort URL format differs.
    """
    try:
        payload = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"ok": False, "error": "invalid JSON"}, status=400)

    columns = payload.get("columns", [])
    if not request.user.is_staff:
        admin_only_keys = {c.key for c in ALL_COLUMNS if c.admin_only}
        columns = [c for c in columns if c.get("key") not in admin_only_keys]
    valid_keys = {c.key for c in ALL_COLUMNS}
    columns = [c for c in columns if isinstance(c, dict) and c.get("key") in valid_keys]

    mode = "admin" if payload.get("mode") == "admin" else "public"
    sort, filters = parse_params(str(payload.get("params", "")), mode)

    request.user.table_pref_json = {
        "columns": columns,
        "sort": sort,
        "filters": filters,
    }
    request.user.save(update_fields=["table_pref_json"])
    return JsonResponse({"ok": True})
