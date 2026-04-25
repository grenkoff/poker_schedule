"""Helpers + middleware to nudge SUPERADMINs into enabling 2FA.

`Soft-enforce`: we never block access. We just add a Django messages
warning once per session so the user sees a banner every fresh login
until they set up TOTP. Hard-enforce (block requests until MFA is set)
is a future option once the team is on it.
"""

from __future__ import annotations

from collections.abc import Callable

from allauth.mfa.models import Authenticator
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Role

SESSION_FLAG = "_mfa_warning_shown"


def user_has_mfa(user) -> bool:
    """True iff the user has at least one active MFA authenticator."""
    if user is None or not user.is_authenticated:
        return False
    return Authenticator.objects.filter(user=user).exists()


def should_nag(request: HttpRequest) -> bool:
    """Whether to add the MFA warning to the messages framework now."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return False
    if user.role != Role.SUPERADMIN:
        return False
    if request.session.get(SESSION_FLAG):
        return False
    # Skip for HTMX partials, AJAX, and the auth/setup paths themselves
    # so the user can land on the MFA page without being interrupted.
    if request.headers.get("HX-Request") == "true":
        return False
    # Skip on auth/MFA setup paths so the user can navigate there without
    # the banner repeating. Path may carry an i18n prefix like /en/accounts/.
    if "/accounts/" in request.path:
        return False
    if request.method != "GET":
        return False
    return not user_has_mfa(user)


class SuperadminMFAReminderMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Add the warning *before* the view runs so the rendered template
        # picks it up in `{% if messages %}` on the same request, not the
        # next one. The session flag still de-dupes per session.
        if should_nag(request):
            url = reverse("mfa_index")
            messages.warning(
                request,
                format_html(
                    str(
                        _(
                            "You are a SUPERADMIN without 2FA enabled. "
                            'Please <a href="{}">set up two-factor</a> for your account.'
                        )
                    ),
                    url,
                ),
            )
            request.session[SESSION_FLAG] = True
        return self.get_response(request)
