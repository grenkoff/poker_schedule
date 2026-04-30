"""Custom form for the Tournament admin.

Headline rule: the editor types `buy_in_without_rake` and `rake`; the
third field, `buy_in_total`, is computed (`without + rake`) and rendered
read-only. Any value the user manages to submit for `buy_in_total` is
ignored server-side.

Money fields are exposed as `DecimalField(max_digits=12, decimal_places=2)`
so the editor sees and types whole-dollar amounts (e.g. `5.25`); we
round-trip to cents at save-time so the model stays in integers.
"""

from __future__ import annotations

import zoneinfo
from decimal import Decimal

from django import forms
from django.contrib.admin.widgets import (
    AdminSplitDateTime,
    BaseAdminDateWidget,
    BaseAdminTimeWidget,
)
from django.utils.translation import gettext_lazy as _

from .models import BlindStructure, Tournament

_GREY_READONLY = {
    "readonly": "readonly",
    "tabindex": "-1",
    "style": "background-color: #f0f0f0; cursor: not-allowed;",
}


class _TournamentDateWidget(BaseAdminDateWidget):
    """`dd.mm.yyyy` date input that still pulls in admin calendar JS.

    `readonly` keeps the input click-focusable (so the popup-trigger JS
    still sees the click) while suppressing the keyboard caret — the only
    edit path is the calendar picker.
    """

    def __init__(self, attrs=None):
        merged = {
            "class": "vDateField tnmt-date-trigger",
            "placeholder": "dd.mm.yyyy",
            "autocomplete": "off",
            "readonly": "readonly",
            "size": "10",
            **(attrs or {}),
        }
        super().__init__(attrs=merged, format="%d.%m.%Y")


class _TournamentTimeWidget(BaseAdminTimeWidget):
    """`hh:mm` time input. Click opens a custom hour/minute picker; the
    input itself is `readonly` so the keyboard caret never appears."""

    def __init__(self, attrs=None):
        merged = {
            "class": "vTimeField tnmt-time-input",
            "size": "5",
            "readonly": "readonly",
            "autocomplete": "off",
            **(attrs or {}),
        }
        super().__init__(attrs=merged, format="%H:%M")


class TournamentSplitDateTimeWidget(AdminSplitDateTime):
    """Tighter `dd.mm.yyyy` + `hh:mm` split widget.

    Subclassing `AdminSplitDateTime` keeps the admin's `split_datetime.html`
    template; subclassing `BaseAdmin{Date,Time}Widget` for the inner
    widgets keeps `calendar.js` + `DateTimeShortcuts.js` in the form's
    media so the calendar popup is wired up.
    """

    def __init__(self, attrs=None):
        widgets = (_TournamentDateWidget(), _TournamentTimeWidget())
        forms.MultiWidget.__init__(self, widgets, attrs)


def _timezone_choices() -> list[tuple[str, str]]:
    """`(value, label)` pairs sorted by current UTC offset.

    Label format mirrors Windows/Linux system pickers, e.g.
    `(UTC+03:00) Europe/Moscow`. The IANA name remains the stored value.
    """
    from datetime import datetime

    now = datetime.now(tz=zoneinfo.ZoneInfo("UTC"))
    rows: list[tuple[int, str, str]] = []
    for name in zoneinfo.available_timezones():
        offset = zoneinfo.ZoneInfo(name).utcoffset(now)
        if offset is None:
            continue
        total_minutes = int(offset.total_seconds() // 60)
        sign = "+" if total_minutes >= 0 else "-"
        h, m = divmod(abs(total_minutes), 60)
        label = f"(UTC{sign}{h:02d}:{m:02d}) {name}"
        rows.append((total_minutes, label, name))
    rows.sort(key=lambda r: (r[0], r[2]))
    return [(name, label) for _, label, name in rows]


class BlindStructureInlineForm(forms.ModelForm):
    """Custom inline form so the `ante` field renders blank instead of `0`.

    The model still defaults to `0`, so an empty submission saves as `0` —
    we just don't pre-fill the input.
    """

    class Meta:
        model = BlindStructure
        fields = ("level", "small_blind", "big_blind", "ante")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ante"].required = False
        self.fields["ante"].initial = None
        # `small_blind` is always derived from `big_blind` via JS — never
        # user-editable. The first row's `big_blind` is also derived
        # (from the parent tournament's starting stack / BB count); the
        # JS hook adds readonly to that single input at runtime.
        self.fields["small_blind"].widget.attrs.update(_GREY_READONLY)

    def clean_ante(self):
        return self.cleaned_data.get("ante") or 0


def _to_cents(value: Decimal | None) -> int | None:
    if value is None:
        return None
    return int((value * 100).to_integral_value())


def _to_dollars(cents: int | None) -> Decimal | None:
    if cents is None:
        return None
    return Decimal(cents) / Decimal(100)


class TournamentAdminForm(forms.ModelForm):
    buy_in_without_rake = forms.DecimalField(
        label=_("Buy-in without rake, $"),
        max_digits=12,
        decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
    )
    rake = forms.DecimalField(
        label=_("Rake, $"),
        max_digits=12,
        decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
    )
    rake_percent = forms.CharField(
        label=_("Rake, %"),
        required=False,
        widget=forms.TextInput(attrs=_GREY_READONLY),
        help_text=_("Auto-computed: rake / (buy-in without rake + rake) x 100."),
    )
    buy_in_total = forms.DecimalField(
        label=_("Buy-in with rake, $"),
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal", **_GREY_READONLY}),
        help_text=_("Auto-computed from buy-in without rake + rake."),
    )
    timezone = forms.ChoiceField(
        label=_("Timezone"),
        choices=_timezone_choices,
        initial="UTC",
        help_text=_("Wall-clock interpretation of the times below."),
    )
    starting_time = forms.SplitDateTimeField(
        label=_("Starting time"),
        widget=TournamentSplitDateTimeWidget(),
        input_date_formats=["%d.%m.%Y"],
        input_time_formats=["%H:%M"],
    )
    late_reg_at = forms.SplitDateTimeField(
        label=_("Late registration closes at"),
        widget=TournamentSplitDateTimeWidget(),
        input_date_formats=["%d.%m.%Y"],
        input_time_formats=["%H:%M"],
    )
    late_registration_duration = forms.CharField(
        label=_("Late registration duration"),
        required=False,
        widget=forms.TextInput(attrs={**_GREY_READONLY, "data-tnmt-duration": "1"}),
        help_text=_("Auto-computed from late registration time minus starting time."),
    )

    class Media:
        js = (
            "admin/js/buyin_autofill.js",
            "admin/js/clear_required_errors.js",
            "admin/js/digits_only.js",
            "admin/js/early_bird_toggle.js",
            "admin/js/time_fieldset.js",
            "admin/js/blind_levels_autonumber.js",
        )
        css = {"all": ("admin/css/tournament_form.css",)}

    class Meta:
        model = Tournament
        # Whitelist every persistable field except the three *_cents columns
        # (handled by the proxy Decimal fields above + clean()).
        fields = (
            "room",
            "name",
            "game_type",
            "guaranteed_dollars",
            "payout_percent",
            "starting_stack",
            "starting_stack_bb",
            "timezone",
            "starting_time",
            "late_registration_available",
            "late_reg_at",
            "late_reg_level",
            "blind_interval_minutes",
            "break_minutes",
            "players_per_table",
            "players_at_final_table",
            "min_players",
            "max_players",
            "re_entry",
            "bubble",
            "periodicity",
            "early_bird",
            "early_bird_type",
            "featured_final_table",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Surface the model-level bounds to the HTML widget. Note: a
        # `setdefault("min", ...)` would be a no-op because Django's
        # `PositiveSmallIntegerField.formfield()` injects `min_value=0`,
        # so the attr already exists. Assign directly to override.
        for name in (
            "late_reg_level",
            "blind_interval_minutes",
            "break_minutes",
            "starting_stack",
            "starting_stack_bb",
        ):
            if name in self.fields:
                self.fields[name].widget.attrs["min"] = "1"
        for name in ("players_per_table", "players_at_final_table"):
            if name in self.fields:
                self.fields[name].widget.attrs["min"] = "2"
                self.fields[name].widget.attrs["max"] = "10"
        for name in ("min_players", "max_players"):
            if name in self.fields:
                self.fields[name].widget.attrs["min"] = "2"
        # Pre-fill the three Decimal fields from existing cents values
        # when editing an existing tournament.
        if self.instance and self.instance.pk:
            self.fields["buy_in_total"].initial = _to_dollars(self.instance.buy_in_total_cents)
            self.fields["buy_in_without_rake"].initial = _to_dollars(
                self.instance.buy_in_without_rake_cents
            )
            self.fields["rake"].initial = _to_dollars(self.instance.rake_cents)
            total_cents = self.instance.buy_in_total_cents
            if total_cents:
                pct = Decimal(self.instance.rake_cents) * Decimal(100) / Decimal(total_cents)
                self.fields["rake_percent"].initial = f"{pct:.2f}"

        # Late-reg fields are conditionally required: the checkbox state
        # decides. On a bound submission with the checkbox unchecked, the
        # date/time/level inputs may be blank — drop their `required`
        # flag so Django doesn't reject the form before clean() can pin
        # safe defaults.
        if self.is_bound:
            available = self.data.get("late_registration_available")
            if not available:
                for name in ("late_reg_at", "late_reg_level"):
                    if name in self.fields:
                        self.fields[name].required = False

    def clean(self):
        cleaned = super().clean()
        without = cleaned.get("buy_in_without_rake")
        rake = cleaned.get("rake")
        if without is not None and rake is not None:
            if without < 0 or rake < 0:
                raise forms.ValidationError(_("Buy-in and rake must be non-negative."))
            cleaned["buy_in_total"] = without + rake

        min_p = cleaned.get("min_players")
        max_p = cleaned.get("max_players")
        if min_p is not None and max_p is not None and max_p < min_p:
            self.add_error(
                "max_players",
                _("Max players cannot be less than min players."),
            )

        starts = cleaned.get("starting_time")
        # When late-reg is disabled the close-time defaults to the start
        # time and the level defaults to 0, so the model-level NOT NULL
        # constraints stay satisfied without forcing the editor to fill
        # the (greyed-out) inputs.
        if cleaned.get("late_registration_available") is False:
            if starts:
                cleaned["late_reg_at"] = starts
                self.errors.pop("late_reg_at", None)
            cleaned["late_reg_level"] = 1
            self.errors.pop("late_reg_level", None)
        else:
            late = cleaned.get("late_reg_at")
            if starts and late and late < starts:
                self.add_error(
                    "late_reg_at",
                    _("Late registration cannot close before the tournament starts."),
                )
        return cleaned

    def save(self, commit=True):
        # Push the three cleaned Decimal values back into the model's cents
        # columns before the underlying ModelForm.save() runs.
        instance = super().save(commit=False)
        instance.buy_in_total_cents = _to_cents(self.cleaned_data["buy_in_total"])
        instance.buy_in_without_rake_cents = _to_cents(self.cleaned_data["buy_in_without_rake"])
        instance.rake_cents = _to_cents(self.cleaned_data["rake"])
        if commit:
            instance.save()
            self.save_m2m()
        return instance
