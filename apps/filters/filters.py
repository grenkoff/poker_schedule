"""Tournament FilterSet for the public list view.

The filter form exposes the subset of Tournament fields users actually
slice by — room, game, format, table size, buy-in range, start window,
late-reg minimum, blind reset. Historical-metric filters (avg entrants,
avg BB at FT) will slot in once those fields are populated in Phase 7.

The buy-in filter takes *major units* (e.g. dollars) for ergonomics; it
converts to cents on its way to the DB.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import django_filters
from django import forms
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

from apps.rooms.models import PokerRoom
from apps.tournaments.models import GameType, TableSize, Tournament, TournamentFormat


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
    tournament_format = django_filters.MultipleChoiceFilter(
        choices=TournamentFormat.choices,
        widget=forms.CheckboxSelectMultiple,
        label=_("Format"),
    )
    table_size = django_filters.MultipleChoiceFilter(
        choices=TableSize.choices,
        widget=forms.CheckboxSelectMultiple,
        label=_("Table size"),
    )

    buy_in_min = django_filters.NumberFilter(
        method="filter_buy_in_min",
        label=_("Min buy-in"),
    )
    buy_in_max = django_filters.NumberFilter(
        method="filter_buy_in_max",
        label=_("Max buy-in"),
    )

    start_from = django_filters.DateTimeFilter(
        field_name="start_at",
        lookup_expr="gte",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        label=_("Start from"),
    )
    start_to = django_filters.DateTimeFilter(
        field_name="start_at",
        lookup_expr="lte",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        label=_("Start to"),
    )

    late_reg_min = django_filters.NumberFilter(
        field_name="late_reg_minutes",
        lookup_expr="gte",
        label=_("Min late reg (min)"),
    )

    blind_reset_at_final = django_filters.BooleanFilter(
        label=_("Blind reset at final table"),
    )

    verified_only = django_filters.BooleanFilter(
        field_name="verified_by_admin",
        label=_("Admin-verified only"),
    )

    class Meta:
        model = Tournament
        fields: list[str] = []  # every filter is declared explicitly above

    # --- buy-in converters --------------------------------------------------
    # Users type "5" meaning $5, not 500 cents. Convert before hitting the DB.

    @staticmethod
    def _to_cents(value: Decimal | float | int) -> int:
        return int(Decimal(value) * 100)

    def filter_buy_in_min(
        self, queryset: QuerySet[Tournament], _name: str, value: Any
    ) -> QuerySet[Tournament]:
        if value in (None, ""):
            return queryset
        return queryset.filter(buy_in_cents__gte=self._to_cents(value))

    def filter_buy_in_max(
        self, queryset: QuerySet[Tournament], _name: str, value: Any
    ) -> QuerySet[Tournament]:
        if value in (None, ""):
            return queryset
        return queryset.filter(buy_in_cents__lte=self._to_cents(value))
