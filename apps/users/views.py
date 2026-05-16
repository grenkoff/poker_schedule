"""Profile management views."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

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
