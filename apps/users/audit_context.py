"""Thread-local request context for audit signals.

Django's pre/post_save signals don't have access to the current `request`,
so when a SUPERADMIN edits a User's role through the admin we'd lose the
"who/where" of the action. This middleware stashes the active request on
a thread-local; the audit signal reads it back. Outside of a request
(CLI, signals, batch jobs) the context is `None` and we record the
change with `changed_by=None` and `source='cli'`.
"""

from __future__ import annotations

from collections.abc import Callable
from threading import local

from django.http import HttpRequest, HttpResponse

_ctx = local()


def get_current_request() -> HttpRequest | None:
    return getattr(_ctx, "request", None)


def set_current_request(request: HttpRequest | None) -> None:
    _ctx.request = request


def clear_current_request() -> None:
    if hasattr(_ctx, "request"):
        del _ctx.request


class AuditContextMiddleware:
    """Stashes `request` on a thread-local for the duration of the call."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        set_current_request(request)
        try:
            return self.get_response(request)
        finally:
            clear_current_request()


def client_ip_from(request: HttpRequest | None) -> str | None:
    """Best-effort IP extraction. Honours `X-Forwarded-For` so it works
    behind Railway's proxy; falls back to `REMOTE_ADDR`."""
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None
