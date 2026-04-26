"""Custom form for the Tournament admin.

Headline rule: editor enters any *two* of the three buy-in fields
(`buy-in (with rake)`, `buy-in (without rake)`, `rake`); the third is
auto-derived. If all three are supplied, they must be consistent —
`with_rake == without_rake + rake`.

Money fields are exposed as `DecimalField(max_digits=12, decimal_places=2)`
so the editor sees and types whole-dollar amounts (e.g. `5.25`); we
round-trip to cents at save-time so the model stays in integers.
"""

from __future__ import annotations

from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Tournament


def _to_cents(value: Decimal | None) -> int | None:
    if value is None:
        return None
    return int((value * 100).to_integral_value())


def _to_dollars(cents: int | None) -> Decimal | None:
    if cents is None:
        return None
    return Decimal(cents) / Decimal(100)


class TournamentAdminForm(forms.ModelForm):
    buy_in_total = forms.DecimalField(
        label=_("Buy-in (with rake), $"),
        max_digits=12,
        decimal_places=2,
        required=False,
    )
    buy_in_without_rake = forms.DecimalField(
        label=_("Buy-in without rake, $"),
        max_digits=12,
        decimal_places=2,
        required=False,
    )
    rake = forms.DecimalField(
        label=_("Rake, $"),
        max_digits=12,
        decimal_places=2,
        required=False,
    )

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
            "early_bird",
            "early_bird_type",
            "featured_final_table",
            "submitted_for_review",
            "verified_by_admin",
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

    def clean(self):
        cleaned = super().clean()
        total = cleaned.get("buy_in_total")
        without = cleaned.get("buy_in_without_rake")
        rake = cleaned.get("rake")

        present = sum(v is not None for v in (total, without, rake))
        if present < 2:
            raise forms.ValidationError(
                _(
                    "Enter at least two of: buy-in (with rake), buy-in (without rake), rake. "
                    "The third one will be derived."
                )
            )

        if total is None:
            total = without + rake
        elif without is None:
            without = total - rake
        elif rake is None:
            rake = total - without
        else:
            # All three given — validate they agree.
            if total != without + rake:
                raise forms.ValidationError(
                    _(
                        "Inconsistent buy-in fields: with-rake (%(t)s) ≠ "
                        "without-rake (%(w)s) + rake (%(r)s)."
                    )
                    % {"t": total, "w": without, "r": rake}
                )

        if min(total, without, rake) < 0:
            raise forms.ValidationError(_("Buy-in and rake must be non-negative."))

        cleaned["buy_in_total"] = total
        cleaned["buy_in_without_rake"] = without
        cleaned["rake"] = rake
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
