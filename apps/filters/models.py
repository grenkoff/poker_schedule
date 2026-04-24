"""SharedFilter — shareable snapshot of a filter state.

Lets a user send a URL that renders the tournament list with specific
filters applied, read-only. The slug is short and URL-safe. `filter_params`
stores the raw querystring so whatever we accept as a filter today is
automatically supported by shared links — no extra migrations when we
add filters later.
"""

from __future__ import annotations

import secrets
from typing import Any

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def _generate_slug() -> str:
    """8-char URL-safe token. ~47 bits of entropy; collisions are retried
    at insert time by the caller."""
    return secrets.token_urlsafe(6)


class SharedFilter(models.Model):
    slug = models.CharField(_("slug"), max_length=32, unique=True, default=_generate_slug)
    name = models.CharField(_("name"), max_length=128, blank=True)
    filter_params = models.TextField(
        _("filter params"),
        help_text=_("URL-encoded querystring snapshot (e.g. game_type=PLO&buy_in_min=10)."),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shared_filters",
        verbose_name=_("created by"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True)

    class Meta:
        verbose_name = _("shared filter")
        verbose_name_plural = _("shared filters")
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.name or self.slug

    def get_absolute_url(self) -> str:
        return reverse("filters:shared", kwargs={"slug": self.slug})

    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at < timezone.now()

    def as_context(self) -> dict[str, Any]:
        return {
            "shared": self,
            "shared_by": self.created_by.email if self.created_by else None,
        }
