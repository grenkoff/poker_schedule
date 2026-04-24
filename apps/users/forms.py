"""User profile form."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import User


class ProfileForm(forms.ModelForm):
    """Edit the logged-in user's display preferences.

    `timezone` is free-form text validated against `zoneinfo`; the
    datalist suggests common zones but anything IANA-valid is accepted.
    An empty submission is treated as "UTC", so users can always reset.
    """

    timezone = forms.CharField(
        required=False,
        label=_("Timezone"),
        widget=forms.TextInput(attrs={"list": "tz-suggestions", "autocomplete": "off"}),
    )

    class Meta:
        model = User
        fields = ("timezone", "preferred_language")

    def clean_timezone(self) -> str:
        value = (self.cleaned_data.get("timezone") or "").strip()
        if not value:
            return "UTC"
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise forms.ValidationError(
                _("Unknown timezone %(value)r. Use an IANA name like Europe/Moscow."),
                params={"value": value},
            ) from exc
        return value


# Curated suggestions for the timezone datalist — shown as autocomplete
# options but the field accepts any IANA name.
TIMEZONE_SUGGESTIONS: tuple[str, ...] = (
    "UTC",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Kyiv",
    "Europe/Moscow",
    "Europe/Istanbul",
    "Asia/Dubai",
    "Asia/Tashkent",
    "Asia/Kolkata",
    "Asia/Bangkok",
    "Asia/Shanghai",
    "Asia/Tokyo",
    "Asia/Seoul",
    "Australia/Sydney",
    "America/Sao_Paulo",
    "America/Argentina/Buenos_Aires",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Mexico_City",
    "America/Vancouver",
    "Pacific/Auckland",
)
