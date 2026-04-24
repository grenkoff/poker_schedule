"""Activate the logged-in user's preferred timezone for the request.

Django stores all datetimes in UTC; this middleware just changes the
*display* timezone so `{{ t.start_at|date:"Y-m-d H:i T" }}` formats in the
user's local time. Anonymous requests keep the project-wide default (UTC).
"""

from __future__ import annotations

from collections.abc import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.http import HttpRequest, HttpResponse
from django.utils import timezone


class UserTimezoneMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = getattr(request, "user", None)
        tz_name = getattr(user, "timezone", None) if user and user.is_authenticated else None
        if tz_name:
            try:
                timezone.activate(ZoneInfo(tz_name))
            except ZoneInfoNotFoundError:
                # Garbage or obsolete TZ on the user row — fall back to UTC
                # rather than 500. A later cleanup job can fix these.
                timezone.deactivate()
        else:
            timezone.deactivate()
        return self.get_response(request)
