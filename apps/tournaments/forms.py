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

from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import BlindStructure, Tournament


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
        widget=forms.TextInput(
            attrs={
                "readonly": "readonly",
                "tabindex": "-1",
                "style": "background-color: #f0f0f0; cursor: not-allowed;",
            }
        ),
        help_text=_("Auto-computed: rake / (buy-in without rake + rake) x 100."),
    )
    buy_in_total = forms.DecimalField(
        label=_("Buy-in with rake, $"),
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(
            attrs={
                "inputmode": "decimal",
                "readonly": "readonly",
                "tabindex": "-1",
                "style": "background-color: #f0f0f0; cursor: not-allowed;",
            }
        ),
        help_text=_("Auto-computed from buy-in without rake + rake."),
    )

    class Media:
        js = (
            "admin/js/buyin_autofill.js",
            "admin/js/clear_required_errors.js",
            "admin/js/digits_only.js",
            "admin/js/early_bird_toggle.js",
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
            "starting_time",
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

    def clean(self):
        cleaned = super().clean()
        without = cleaned.get("buy_in_without_rake")
        rake = cleaned.get("rake")

        if without is None or rake is None:
            return cleaned

        if without < 0 or rake < 0:
            raise forms.ValidationError(_("Buy-in and rake must be non-negative."))

        cleaned["buy_in_total"] = without + rake
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
