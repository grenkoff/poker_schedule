"""Custom form for the Tournament admin.

Headline rule: the editor types `buy_in_without_rake` and `rake`; the
third field, `buy_in_total`, is computed (`without + rake`) and rendered
read-only. Any value the user manages to submit for `buy_in_total` is
ignored server-side.
"""

from __future__ import annotations

import json
import zoneinfo
from decimal import Decimal

from django import forms
from django.contrib.admin.widgets import (
    AdminSplitDateTime,
    BaseAdminDateWidget,
    BaseAdminTimeWidget,
)
from django.utils import timezone as djtz
from django.utils.translation import gettext_lazy as _

from .models import BlindLevelTemplate, BlindStructure, BlindStructureTemplate, Tournament

_GREY_READONLY = {
    "readonly": "readonly",
    "tabindex": "-1",
    "style": "background-color: #f0f0f0; cursor: not-allowed;",
}


_WEEKDAY_CHOICES = (
    (0, _("Mon")),
    (1, _("Tue")),
    (2, _("Wed")),
    (3, _("Thu")),
    (4, _("Fri")),
    (5, _("Sat")),
    (6, _("Sun")),
)


class WeekdaysBitmaskField(forms.MultipleChoiceField):
    """Renders the 7-bit `Tournament.weekdays` mask as Mon..Sun checkboxes.

    Model holds an int (bit i = Python weekday i, Mon=0..Sun=6); form
    presents it as a list of selected ints and packs back to int on clean.
    Empty submissions are returned as 0 so the cross-field clean() in
    `TournamentAdminForm` can decide whether that's acceptable (one-off)
    or not (recurring).
    """

    widget = forms.CheckboxSelectMultiple

    def __init__(self, **kwargs):
        kwargs.setdefault("choices", _WEEKDAY_CHOICES)
        kwargs.setdefault("required", False)
        kwargs.setdefault("initial", 0b1111111)
        super().__init__(**kwargs)

    def prepare_value(self, value):
        if isinstance(value, int):
            return [str(i) for i in range(7) if value & (1 << i)]
        return super().prepare_value(value)

    def clean(self, value):
        picked = super().clean(value)
        mask = 0
        for raw in picked:
            mask |= 1 << int(raw)
        return mask

    def has_changed(self, initial, data):
        # Django's MultipleChoiceField.has_changed calls len() on initial,
        # but our model stores a bitmask int — expand it to the list shape
        # the parent expects.
        if isinstance(initial, int):
            initial = self.prepare_value(initial)
        return super().has_changed(initial, data)


class PeriodicityWidget(forms.Select):
    """Stock Select that tags each <option> with data-interval-seconds.

    The Tournament admin form's weekday JS reads this attribute off the
    currently-selected option to decide whether the weekday checkboxes
    should be enabled (recurring) or disabled (one-off / no selection).
    """

    def __init__(self, attrs=None):
        merged = {"data-tnmt-periodicity": "1", **(attrs or {})}
        super().__init__(attrs=merged)
        self._interval_map: dict[int, int] | None = None

    def _intervals(self) -> dict[int, int]:
        if self._interval_map is None:
            from .models import Periodicity

            self._interval_map = dict(Periodicity.objects.values_list("pk", "interval_seconds"))
        return self._interval_map

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        pk = getattr(value, "value", value)
        if pk not in (None, ""):
            interval = self._intervals().get(int(pk))
            if interval is not None:
                option["attrs"]["data-interval-seconds"] = str(interval)
        return option


class TournamentSeriesWidget(forms.Select):
    """Series Select tagged with data-room-id on each <option>.

    The Tournament admin form lists every series across every room;
    `series_filter.js` reads `data-room-id` and hides options whose
    room doesn't match the currently-selected Room.
    """

    def __init__(self, attrs=None):
        merged = {"data-tnmt-series": "1", **(attrs or {})}
        super().__init__(attrs=merged)
        self._room_map: dict[int, int] | None = None

    def _rooms(self) -> dict[int, int]:
        if self._room_map is None:
            from .models import TournamentSeries

            self._room_map = dict(TournamentSeries.objects.values_list("pk", "room_id"))
        return self._room_map

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        pk = getattr(value, "value", value)
        if pk not in (None, ""):
            room_id = self._rooms().get(int(pk))
            if room_id is not None:
                option["attrs"]["data-room-id"] = str(room_id)
        return option


class BlindStructureTemplateWidget(forms.Select):
    """Template Select that tags each <option> with `data-levels="[...]"`.

    The Tournament admin form's prefill JS reads this attribute off the
    selected option and replaces the BLIND LEVELS inline rows with the
    template's rows. Template payloads are small (a few dozen ints), so
    embedding them on the page is cheaper than an AJAX round-trip and
    avoids a race with the inline-formset add/remove machinery.
    """

    def __init__(self, attrs=None):
        merged = {"data-tnmt-template": "1", **(attrs or {})}
        super().__init__(attrs=merged)
        self._levels_map: dict[int, list[list[int]]] | None = None

    def _levels(self) -> dict[int, list[list[int]]]:
        if self._levels_map is None:
            rows = BlindLevelTemplate.objects.order_by("template_id", "level").values_list(
                "template_id",
                "level",
                "small_blind",
                "big_blind",
                "ante",
            )
            by_tpl: dict[int, list[list[int]]] = {}
            for tpl_id, level, sb, bb, ante in rows:
                by_tpl.setdefault(tpl_id, []).append([level, sb, bb, ante])
            self._levels_map = by_tpl
        return self._levels_map

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        pk = getattr(value, "value", value)
        if pk not in (None, ""):
            levels = self._levels().get(int(pk))
            if levels is not None:
                option["attrs"]["data-levels"] = json.dumps(levels)
        return option


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


_BLIND_INPUT_WIDTH = "width: 10em;"


class _BlindRowFormMixin:
    """Shared init for the two blind-level inline forms.

    Both `BlindStructure` (per-tournament rows) and `BlindLevelTemplate`
    (reusable template rows) share the same column shape and UX: ante
    starts blank instead of zero, and `small_blind` is read-only because
    it's derived from `big_blind` client-side via JS.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ante"].required = False
        self.fields["ante"].initial = None
        # SB/BB/ante regularly hold 7-8 digit values in high-stakes
        # structures; the default ~10ch width clips them. Roughly 2x
        # the admin default.
        self.fields["big_blind"].widget.attrs["style"] = _BLIND_INPUT_WIDTH
        self.fields["ante"].widget.attrs["style"] = _BLIND_INPUT_WIDTH
        sb_attrs = dict(_GREY_READONLY)
        sb_attrs["style"] = sb_attrs["style"] + " " + _BLIND_INPUT_WIDTH
        self.fields["small_blind"].widget.attrs.update(sb_attrs)

    def clean_ante(self):
        return self.cleaned_data.get("ante") or 0


class BlindStructureInlineForm(_BlindRowFormMixin, forms.ModelForm):
    class Meta:
        model = BlindStructure
        fields = ("level", "small_blind", "big_blind", "ante")


class BlindLevelTemplateInlineForm(_BlindRowFormMixin, forms.ModelForm):
    class Meta:
        model = BlindLevelTemplate
        fields = ("level", "small_blind", "big_blind", "ante")


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
    weekdays = WeekdaysBitmaskField(label=_("Active weekdays"))
    apply_template = forms.ModelChoiceField(
        label=_("Load from existing blind structure"),
        queryset=BlindStructureTemplate.objects.all().order_by("name"),
        required=False,
        widget=BlindStructureTemplateWidget(),
        help_text=_(
            "Pick a saved template to replace the BLIND LEVELS rows below "
            "with its rows. The template itself is unaffected by later "
            "edits to this tournament."
        ),
    )
    save_as_template = forms.BooleanField(
        label=_("Save current blind structure as a new template"),
        required=False,
    )
    save_as_template_name = forms.CharField(
        label=_("New template name"),
        max_length=120,
        required=False,
        help_text=_(
            "Leave blank to auto-name from the structure's shape "
            "(e.g. '1-100(12)_5-1,600(150)'). If an identical structure "
            "already exists no new template is created."
        ),
    )

    class Media:
        js = (
            # integer_thousand_seps must load BEFORE blind_levels_autonumber
            # so it converts integer inputs to type=text before autonumber
            # dispatches input events that the formatter listens for.
            "admin/js/integer_thousand_seps.js",
            "admin/js/buyin_autofill.js",
            "admin/js/clear_required_errors.js",
            "admin/js/digits_only.js",
            "admin/js/time_fieldset.js",
            "admin/js/blind_levels_autonumber.js",
            "admin/js/blind_template_apply.js",
            "admin/js/weekdays_presets.js",
        )
        css = {"all": ("admin/css/tournament_form.css", "admin/css/blind_inline.css")}

    class Meta:
        model = Tournament
        # Whitelist every persistable field except the three *_cents columns
        # (handled by the proxy Decimal fields above + clean()).
        fields = (
            "room",
            "series",
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
            "weekdays",
            "early_bird_type",
            "featured_final_table",
            "deal_making",
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
                self.fields[name].widget.attrs["min"] = "1"
        if self.instance and self.instance.pk:
            self.fields["buy_in_total"].initial = self.instance.buy_in_total
            self.fields["buy_in_without_rake"].initial = self.instance.buy_in_without_rake
            self.fields["rake"].initial = self.instance.rake
            if self.instance.buy_in_total:
                pct = self.instance.rake * Decimal(100) / self.instance.buy_in_total
                self.fields["rake_percent"].initial = f"{pct:.2f}"
            # Display starting_time / late_reg_at in the tournament's own
            # timezone (the value the editor originally typed), not in
            # whatever the active request TZ happens to be. We strip
            # tzinfo so the SplitDateTime widget renders the components
            # directly without re-converting.
            instance_tz = self.instance.timezone
            if instance_tz:
                try:
                    tz = zoneinfo.ZoneInfo(instance_tz)
                except zoneinfo.ZoneInfoNotFoundError:
                    tz = None
                if tz is not None:
                    for fname in ("starting_time", "late_reg_at"):
                        val = getattr(self.instance, fname, None)
                        if val and djtz.is_aware(val):
                            self.initial[fname] = val.astimezone(tz).replace(tzinfo=None)

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

        # Interpret the wall-clock datetimes the editor typed as living
        # in the timezone they picked above, NOT in the request's active
        # TZ (which is the logged-in admin's profile TZ — unrelated to
        # the tournament's local time). SplitDateTimeField has already
        # run `from_current_timezone` and made the value aware, but the
        # wall-clock components match what the editor typed, so we strip
        # tzinfo and re-anchor in the picked zone.
        tz_name = cleaned.get("timezone")
        if tz_name:
            try:
                tz = zoneinfo.ZoneInfo(tz_name)
            except zoneinfo.ZoneInfoNotFoundError:
                tz = None
            if tz is not None:
                for fname in ("starting_time", "late_reg_at"):
                    val = cleaned.get(fname)
                    if val:
                        wallclock = val.replace(tzinfo=None) if djtz.is_aware(val) else val
                        cleaned[fname] = djtz.make_aware(wallclock, tz)

        # Series must belong to the same room as the tournament.
        room = cleaned.get("room")
        series = cleaned.get("series")
        if room is not None and series is not None and series.room_id != room.pk:
            self.add_error(
                "series",
                _("Pick a series that belongs to the selected room."),
            )

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

        # Weekday handling. The field is rendered as disabled checkboxes
        # whenever the periodicity is unset or one-off, so the POST may
        # be empty in those cases — substitute the all-days default so
        # the model has a sensible value either way. For recurring
        # periodicities the editor must actively pick at least one day
        # AND the master's own starting weekday must be in the set.
        periodicity = cleaned.get("periodicity")
        weekdays_mask = cleaned.get("weekdays") or 0
        if periodicity is None or periodicity.interval_seconds == 0:
            cleaned["weekdays"] = 0b1111111
        else:
            if weekdays_mask == 0:
                self.add_error("weekdays", _("Pick at least one weekday."))
            elif starts is not None and not (weekdays_mask & (1 << starts.weekday())):
                self.add_error(
                    "weekdays",
                    _("Starting time falls on a weekday that isn't selected."),
                )

        # When `save_as_template` is checked, validate the supplied name
        # only if non-empty; the admin's `_auto_template_name` will fill
        # in a default otherwise.
        if cleaned.get("save_as_template"):
            name = (cleaned.get("save_as_template_name") or "").strip()
            if name and BlindStructureTemplate.objects.filter(name=name).exists():
                self.add_error(
                    "save_as_template_name",
                    _("A template with that name already exists."),
                )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.buy_in_total = self.cleaned_data["buy_in_total"]
        instance.buy_in_without_rake = self.cleaned_data["buy_in_without_rake"]
        instance.rake = self.cleaned_data["rake"]
        # Derive the `early_bird` boolean from the (now optional) type
        # dropdown — picking any type means early-bird is active; leaving
        # it blank means it's not.
        instance.early_bird = bool(self.cleaned_data.get("early_bird_type"))
        if commit:
            instance.save()
            self.save_m2m()
        return instance
