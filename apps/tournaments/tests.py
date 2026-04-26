"""Tests for tournament models: helpers, relations, blind levels."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.rooms.models import PokerRoom
from apps.tournaments.models import (
    BlindStructure,
    BubbleOption,
    EarlyBirdType,
    GameType,
    ReEntryOption,
    Tournament,
)


@pytest.fixture
def pokerok() -> PokerRoom:
    return PokerRoom.objects.get(slug="pokerok")


def _make_tournament(room: PokerRoom, **overrides) -> Tournament:
    defaults = {
        "room": room,
        "name": "Test Tournament",
        "game_type": GameType.NLHE,
        "buy_in_total_cents": 1100,
        "buy_in_without_rake_cents": 1000,
        "rake_cents": 100,
        "guaranteed_dollars": 10000,
        "payout_percent": 15,
        "starting_stack": 10000,
        "starting_stack_bb": 50,
        "starting_time": datetime(2026, 5, 1, 19, 0, tzinfo=UTC),
        "late_reg_at": datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
        "late_reg_level": 12,
        "blind_interval_minutes": 10,
        "break_minutes": 5,
        "players_per_table": 9,
        "players_at_final_table": 9,
        "min_players": 2,
        "max_players": 1000,
        "re_entry": ReEntryOption.objects.get(name="unlimited"),
        "bubble": BubbleOption.objects.get(name="finalized_when_registration_closes"),
        "early_bird": False,
        "early_bird_type": EarlyBirdType.objects.get(name="compensated_at_bubble"),
        "featured_final_table": False,
    }
    defaults.update(overrides)
    return Tournament.objects.create(**defaults)


@pytest.mark.django_db
def test_tournament_str_includes_room_and_name(pokerok):
    tournament = _make_tournament(pokerok, name="Daily $11 Bounty")
    assert str(tournament) == "Pokerok — Daily $11 Bounty"


@pytest.mark.django_db
def test_tournament_money_decimal_properties(pokerok):
    tournament = _make_tournament(
        pokerok,
        buy_in_total_cents=1100,
        buy_in_without_rake_cents=1000,
        rake_cents=100,
    )
    assert tournament.buy_in_total == Decimal("11.00")
    assert tournament.buy_in_without_rake == Decimal("10.00")
    assert tournament.rake == Decimal("1.00")


@pytest.mark.django_db
def test_tournament_workflow_defaults(pokerok):
    t = _make_tournament(pokerok)
    assert t.submitted_for_review is False
    assert t.verified_by_admin is False


@pytest.mark.django_db
def test_blind_level_unique_per_tournament(pokerok):
    tournament = _make_tournament(pokerok)
    BlindStructure.objects.create(tournament=tournament, level=1, small_blind=10, big_blind=20)
    with pytest.raises(IntegrityError):
        BlindStructure.objects.create(tournament=tournament, level=1, small_blind=15, big_blind=30)


@pytest.mark.django_db
def test_blind_levels_independent_across_tournaments(pokerok):
    t1 = _make_tournament(pokerok, name="A")
    t2 = _make_tournament(
        pokerok,
        name="B",
        starting_time=datetime(2026, 5, 1, 19, 0, tzinfo=UTC) + timedelta(hours=1),
    )
    BlindStructure.objects.create(tournament=t1, level=1, small_blind=10, big_blind=20)
    BlindStructure.objects.create(tournament=t2, level=1, small_blind=10, big_blind=20)
    assert BlindStructure.objects.count() == 2


@pytest.mark.django_db
def test_deleting_tournament_cascades_to_blind_levels(pokerok):
    tournament = _make_tournament(pokerok)
    BlindStructure.objects.create(tournament=tournament, level=1, small_blind=10, big_blind=20)
    tournament.delete()
    assert BlindStructure.objects.count() == 0


@pytest.mark.django_db
def test_option_models_seeded():
    """The 0002_seed_options migration plants the defaults."""
    assert ReEntryOption.objects.filter(name="unlimited").exists()
    assert BubbleOption.objects.filter(name="finalized_when_registration_closes").exists()
    assert EarlyBirdType.objects.filter(name="compensated_at_bubble").exists()
