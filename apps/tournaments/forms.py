"""Custom form for the Tournament admin.

Headline rule: the editor types `buy_in_without_rake` and `rake`; the
third field, `buy_in_total`, is computed (`without + rake`) and rendered
read-only. Any value the user manages to submit for `buy_in_total` is
ignored server-side.
"""

from __future__ import annotations

import json
import zoneinfo
from datetime import datetime, timedelta
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


# Sentinel returned by OptionalDateSplitDateTimeField.compress when only the
# time half was submitted (recurring tournaments hide the date input).
TIME_ONLY = "__TIME_ONLY__"


class OptionalDateSplitDateTimeField(forms.SplitDateTimeField):
    """Split date+time field whose DATE half may be blank.

    For recurring tournaments the date input is hidden (only the time-of-day
    matters), so the POST carries just the time. When that happens we return a
    ``(TIME_ONLY, datetime.time)`` marker that `TournamentAdminForm.clean()`
    turns into a concrete UTC `starting_time`/`late_reg_at` by synthesizing the
    anchor date. With a date present it behaves exactly like the parent.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Per-subfield required flags (the parent's require_all_fields=True
        # had reset both to False): date optional, time required.
        self.require_all_fields = False
        self.fields[0].required = False
        self.fields[1].required = True

    def compress(self, data_list):
        if not data_list:
            return None
        date_part, time_part = data_list
        if date_part in (None, "") and time_part not in (None, ""):
            return (TIME_ONLY, time_part)
        return super().compress(data_list)


# One representative IANA zone per whole-hour UTC offset, mirroring the public
# list's picker (static/js/localize_times.js) so the admin shows each timezone
# once instead of every IANA name (which duplicates offsets many times over).
# (iana_name, fixed_offset_minutes, city_label)
_TZ_CHOICES_RAW: tuple[tuple[str, int, str], ...] = (
    ("Etc/GMT+12", -720, "Baker Island"),
    ("Pacific/Pago_Pago", -660, "Pago Pago"),
    ("Pacific/Honolulu", -600, "Honolulu"),
    ("America/Anchorage", -540, "Anchorage"),
    ("America/Los_Angeles", -480, "Los Angeles"),
    ("America/Denver", -420, "Denver"),
    ("America/Mexico_City", -360, "Mexico City"),
    ("America/New_York", -300, "New York"),
    ("America/Santiago", -240, "Santiago"),
    ("America/Sao_Paulo", -180, "São Paulo"),
    ("Atlantic/South_Georgia", -120, "South Georgia"),
    ("Atlantic/Azores", -60, "Azores"),
    ("UTC", 0, "UTC"),
    ("Europe/Berlin", 60, "Berlin"),
    ("Europe/Athens", 120, "Athens"),
    ("Europe/Moscow", 180, "Moscow"),
    ("Asia/Dubai", 240, "Dubai"),
    ("Asia/Almaty", 300, "Almaty"),
    ("Asia/Dhaka", 360, "Dhaka"),
    ("Asia/Bangkok", 420, "Bangkok"),
    ("Asia/Singapore", 480, "Singapore"),
    ("Asia/Tokyo", 540, "Tokyo"),
    ("Australia/Sydney", 600, "Sydney"),
    ("Pacific/Noumea", 660, "Nouméa"),
    ("Pacific/Auckland", 720, "Auckland"),
    ("Pacific/Apia", 780, "Apia"),
    ("Pacific/Kiritimati", 840, "Kiritimati"),
)


def _timezone_choices() -> list[tuple[str, str]]:
    """`(iana_name, label)` pairs — one per UTC offset, e.g.
    `("Europe/Moscow", "(UTC+03:00) Moscow")`."""
    rows = []
    for name, mins, city in _TZ_CHOICES_RAW:
        sign = "+" if mins >= 0 else "-"
        h, m = divmod(abs(mins), 60)
        rows.append((name, f"(UTC{sign}{h:02d}:{m:02d}) {city}"))
    return rows


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
        label=_("Buy-in to prize pool, $"),
        max_digits=12,
        decimal_places=2,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
    )
    bounty_buyin = forms.DecimalField(
        label=_("Buy-in to bounty pool, $"),
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
        help_text=_("Leave at 0 for non-bounty tournaments."),
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
        help_text=_("Auto-computed: prize-pool buy-in + bounty buy-in + rake."),
    )
    min_bounty = forms.DecimalField(
        label=_("Minimum bounty, $"),
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={"inputmode": "decimal"}),
    )
    timezone = forms.ChoiceField(
        label=_("Timezone"),
        choices=_timezone_choices,
        initial="UTC",
        help_text=_("Wall-clock interpretation of the times below."),
    )
    starting_time = OptionalDateSplitDateTimeField(
        label=_("Starting time"),
        widget=TournamentSplitDateTimeWidget(),
        input_date_formats=["%d.%m.%Y"],
        input_time_formats=["%H:%M"],
    )
    late_reg_at = OptionalDateSplitDateTimeField(
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

    class Media:
        js = (
            # integer_thousand_seps must load BEFORE blind_levels_autonumber
            # so it converts integer inputs to type=text before autonumber
            # dispatches input events that the formatter listens for.
            "admin/js/integer_thousand_seps.js",
            # integer_spinners must load AFTER integer_thousand_seps so the
            # inputs are already type=text + data-int-format when it wraps them.
            "admin/js/integer_spinners.js",
            "admin/js/buyin_autofill.js",
            "admin/js/clear_required_errors.js",
            "admin/js/digits_only.js",
            "admin/js/time_fieldset.js",
            "admin/js/blind_levels_autonumber.js",
            "admin/js/blind_template_apply.js",
            "admin/js/weekdays_presets.js",
        )
        css = {
            "all": (
                "admin/css/tournament_form.css",
                "admin/css/blind_inline.css",
                "admin/css/integer_spinners.css",
            )
        }

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
            "bounty_type",
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
            self.fields["bounty_buyin"].initial = self.instance.bounty_buyin
            self.fields["rake"].initial = self.instance.rake
            self.fields["min_bounty"].initial = self.instance.min_bounty
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
                # Keep a previously-stored zone selectable even if it's not in
                # the curated one-per-offset list (so editing never silently
                # changes it).
                tz_field = self.fields["timezone"]
                if instance_tz not in {c[0] for c in tz_field.choices}:
                    tz_field.choices = [(instance_tz, instance_tz), *tz_field.choices]
                try:
                    tz = zoneinfo.ZoneInfo(instance_tz)
                except zoneinfo.ZoneInfoNotFoundError:
                    tz = None
                if tz is not None:
                    for fname in ("starting_time", "late_reg_at"):
                        val = getattr(self.instance, fname, None)
                        if val and djtz.is_aware(val):
                            self.initial[fname] = val.astimezone(tz).replace(tzinfo=None)

            # Preselect the existing template that matches this
            # tournament's blind structure so the editor sees the name
            # of the template they're effectively using. The save_related
            # path skips a re-apply when the signature is already
            # equal, so a no-op edit doesn't churn the inline rows.
            from .models import blind_signature, template_id_for_signature

            sig = blind_signature(self.instance.blind_levels.all())
            if sig:
                matched = template_id_for_signature(sig)
                if matched is not None:
                    self.fields["apply_template"].initial = matched

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

        # --- shared checks, independent of one-off vs recurring ----------
        room = cleaned.get("room")
        series = cleaned.get("series")
        if room is not None and series is not None and series.room_id != room.pk:
            self.add_error(
                "series",
                _("Pick a series that belongs to the selected room."),
            )

        without = cleaned.get("buy_in_without_rake")
        bounty = cleaned.get("bounty_buyin") or Decimal(0)
        rake = cleaned.get("rake")
        if without is not None and rake is not None:
            if without < 0 or bounty < 0 or rake < 0:
                raise forms.ValidationError(_("Buy-in parts must be non-negative."))
            cleaned["buy_in_total"] = without + bounty + rake
        min_bounty = cleaned.get("min_bounty")
        if min_bounty is not None and min_bounty < 0:
            self.add_error("min_bounty", _("Minimum bounty must be non-negative."))

        min_p = cleaned.get("min_players")
        max_p = cleaned.get("max_players")
        if min_p is not None and max_p is not None and max_p < min_p:
            self.add_error(
                "max_players",
                _("Max players cannot be less than min players."),
            )

        # --- time + recurrence -------------------------------------------
        # The editor types wall-clock times in the picked timezone. For a
        # recurring tournament only the time-of-day + weekdays matter (the
        # date input is hidden); for a one-off the full date+time is used.
        tz = None
        tz_name = cleaned.get("timezone")
        if tz_name:
            try:
                tz = zoneinfo.ZoneInfo(tz_name)
            except zoneinfo.ZoneInfoNotFoundError:
                tz = None

        periodicity = cleaned.get("periodicity")
        recurring = periodicity is not None and periodicity.interval_seconds > 0
        late_available = cleaned.get("late_registration_available") is not False

        if recurring:
            if tz is None:
                self.add_error("timezone", _("Pick a timezone."))
            else:
                self._clean_recurring(cleaned, tz, late_available)
        else:
            self._clean_one_off(cleaned, tz, late_available)

        return cleaned

    def _typed_time(self, cleaned, fname):
        """The local wall-clock time-of-day the editor entered for `fname`,
        regardless of whether the date was present (one-off) or omitted
        (recurring → `OptionalDateSplitDateTimeField` TIME_ONLY marker)."""
        val = cleaned.get(fname)
        if isinstance(val, tuple) and len(val) == 2 and val[0] == TIME_ONLY:
            return val[1]
        if isinstance(val, datetime):
            return val.time()
        raw = (self.data.get(fname + "_1") or "").strip()
        if raw:
            try:
                return datetime.strptime(raw, "%H:%M").time()
            except ValueError:
                return None
        return None

    def _clean_recurring(self, cleaned, tz, late_available):
        """Recurring tournament: store an absolute UTC anchor near `now`
        whose LOCAL time-of-day + weekday match what the editor entered.
        Weekdays are stored in the tournament's own timezone frame."""
        mask = cleaned.get("weekdays") or 0
        if mask == 0:
            self.add_error("weekdays", _("Pick at least one weekday."))
            return
        allowed = {i for i in range(7) if mask & (1 << i)}

        start_t = self._typed_time(cleaned, "starting_time")
        if start_t is None:
            self.add_error("starting_time", _("Enter a start time."))
            return

        # Anchor: the soonest local date (>= today) on an allowed weekday.
        today = djtz.now().astimezone(tz).date()
        anchor_date = next(
            today + timedelta(days=n)
            for n in range(8)
            if (today + timedelta(days=n)).weekday() in allowed
        )
        cleaned["starting_time"] = djtz.make_aware(datetime.combine(anchor_date, start_t), tz)
        self.errors.pop("starting_time", None)

        if not late_available:
            cleaned["late_reg_at"] = cleaned["starting_time"]
            cleaned["late_reg_level"] = 1
            self.errors.pop("late_reg_at", None)
            self.errors.pop("late_reg_level", None)
            return

        late_t = self._typed_time(cleaned, "late_reg_at")
        if late_t is None:
            self.add_error("late_reg_at", _("Enter a late-registration time."))
            return
        late_naive = datetime.combine(anchor_date, late_t)
        if late_t <= start_t:  # closes the next day
            late_naive += timedelta(days=1)
        cleaned["late_reg_at"] = djtz.make_aware(late_naive, tz)
        self.errors.pop("late_reg_at", None)

    def _clean_one_off(self, cleaned, tz, late_available):
        """One-off tournament: keep the typed wall-clock date+time, just
        re-anchor it into the picked timezone (not the request's TZ)."""
        if tz is not None:
            for fname in ("starting_time", "late_reg_at"):
                val = cleaned.get(fname)
                if isinstance(val, datetime):
                    wallclock = val.replace(tzinfo=None) if djtz.is_aware(val) else val
                    cleaned[fname] = djtz.make_aware(wallclock, tz)

        cleaned["weekdays"] = 0b1111111

        starts = cleaned.get("starting_time")
        if not late_available:
            if isinstance(starts, datetime):
                cleaned["late_reg_at"] = starts
                self.errors.pop("late_reg_at", None)
            cleaned["late_reg_level"] = 1
            self.errors.pop("late_reg_level", None)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.buy_in_total = self.cleaned_data["buy_in_total"]
        instance.buy_in_without_rake = self.cleaned_data["buy_in_without_rake"]
        instance.bounty_buyin = self.cleaned_data.get("bounty_buyin") or Decimal(0)
        instance.rake = self.cleaned_data["rake"]
        instance.min_bounty = self.cleaned_data.get("min_bounty")
        # Derive the `early_bird` / `is_bounty` booleans from their (optional)
        # type dropdowns — picking any value means the feature is active.
        instance.early_bird = bool(self.cleaned_data.get("early_bird_type"))
        instance.is_bounty = bool(self.cleaned_data.get("bounty_type"))
        if commit:
            instance.save()
            self.save_m2m()
        return instance
