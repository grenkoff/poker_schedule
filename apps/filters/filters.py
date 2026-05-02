"""Tournament FilterSet for the public list view.

Surfaces the slice users actually narrow by — room, game, buy-in range,
starting time window, re-entry / bubble policy, and featured FT. Buy-in
input is in major units (dollars). Verification is enforced server-side
in the view's base queryset, so unverified tournaments never reach the
filter.
"""

from __future__ import annotations

from typing import Any

import django_filters
from django import forms
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from apps.rooms.models import PokerRoom
from apps.tournaments.models import (
    BubbleOption,
    EarlyBirdType,
    GameType,
    ReEntryOption,
    Tournament,
)


class TournamentFilter(django_filters.FilterSet):
    rooms = django_filters.ModelMultipleChoiceFilter(
        queryset=PokerRoom.objects.filter(is_active=True),
        field_name="room",
        widget=forms.CheckboxSelectMultiple,
        label=_("Rooms"),
    )
    game_type = django_filters.MultipleChoiceFilter(
        choices=GameType.choices,
        widget=forms.CheckboxSelectMultiple,
        label=_("Game"),
    )
    re_entry = django_filters.ModelMultipleChoiceFilter(
        queryset=ReEntryOption.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label=_("Re-entry"),
    )
    bubble = django_filters.ModelMultipleChoiceFilter(
        queryset=BubbleOption.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label=_("Bubble"),
    )
    early_bird_type = django_filters.ModelMultipleChoiceFilter(
        queryset=EarlyBirdType.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label=_("Early bird type"),
    )

    buy_in_min = django_filters.NumberFilter(
        method="filter_buy_in_min",
        label=_("Min buy-in"),
    )
    buy_in_max = django_filters.NumberFilter(
        method="filter_buy_in_max",
        label=_("Max buy-in"),
    )

    starting_from = django_filters.DateTimeFilter(
        field_name="starting_time",
        lookup_expr="gte",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        label=_("Starts from"),
    )
    starting_to = django_filters.DateTimeFilter(
        field_name="starting_time",
        lookup_expr="lte",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        label=_("Starts to"),
    )

    early_bird = django_filters.BooleanFilter(label=_("Early bird"))
    featured_final_table = django_filters.BooleanFilter(label=_("Featured FT"))

    class Meta:
        model = Tournament
        fields: list[str] = []  # every filter is declared explicitly above

    def filter_buy_in_min(
        self, queryset: QuerySet[Tournament], _name: str, value: Any
    ) -> QuerySet[Tournament]:
        if value in (None, ""):
            return queryset
        return queryset.filter(buy_in_total__gte=value)

    def filter_buy_in_max(
        self, queryset: QuerySet[Tournament], _name: str, value: Any
    ) -> QuerySet[Tournament]:
        if value in (None, ""):
            return queryset
        return queryset.filter(buy_in_total__lte=value)
