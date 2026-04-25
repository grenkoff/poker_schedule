"""Tests for tournament models: constraints, helpers, relations."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.rooms.models import PokerRoom
from apps.tournaments.models import (
    BlindStructure,
    GameType,
    TableSize,
    Tournament,
    TournamentFormat,
    TournamentResult,
)


@pytest.fixture
def pokerok() -> PokerRoom:
    """The MVP-seeded Pokerok room (from the rooms data migration)."""
    return PokerRoom.objects.get(slug="pokerok")


def _make_tournament(room: PokerRoom, **overrides) -> Tournament:
    defaults = {
        "room": room,
        "external_id": "ext-1",
        "name": "Daily $10 Bounty",
        "game_type": GameType.NLHE,
        "tournament_format": TournamentFormat.PKO,
        "table_size": TableSize.NINE_MAX,
        "buy_in_cents": 1000,
        "rake_cents": 100,
        "currency": "USD",
        "start_at": datetime(2026, 5, 1, 19, 0, tzinfo=UTC),
        "late_reg_minutes": 60,
        "blind_level_minutes": 10,
    }
    defaults.update(overrides)
    return Tournament.objects.create(**defaults)


@pytest.mark.django_db
def test_tournament_str_includes_room_and_name(pokerok):
    tournament = _make_tournament(pokerok)
    assert str(tournament) == "Pokerok — Daily $10 Bounty"


@pytest.mark.django_db
def test_tournament_buy_in_and_total_cost_properties(pokerok):
    tournament = _make_tournament(pokerok, buy_in_cents=1000, rake_cents=100)
    assert tournament.buy_in == Decimal("10.00")
    assert tournament.total_cost == Decimal("11.00")


@pytest.mark.django_db
def test_tournament_room_external_id_is_unique(pokerok):
    _make_tournament(pokerok, external_id="dup")
    with pytest.raises(IntegrityError):
        _make_tournament(pokerok, external_id="dup", name="Another")


@pytest.mark.django_db
def test_tournament_same_external_id_allowed_across_rooms(pokerok):
    pokerdom = PokerRoom.objects.get(slug="pokerdom")
    _make_tournament(pokerok, external_id="shared")
    _make_tournament(pokerdom, external_id="shared")
    assert Tournament.objects.filter(external_id="shared").count() == 2


@pytest.mark.django_db
def test_tournament_defaults_are_sensible(pokerok):
    t = _make_tournament(pokerok)
    assert t.final_table_size == 9
    assert t.blind_reset_at_final is False
    assert t.verified_by_admin is False
    assert t.avg_entrants is None


@pytest.mark.django_db
def test_blind_structure_level_is_unique_per_tournament(pokerok):
    tournament = _make_tournament(pokerok)
    BlindStructure.objects.create(tournament=tournament, level=1, small_blind=10, big_blind=20)
    with pytest.raises(IntegrityError):
        BlindStructure.objects.create(tournament=tournament, level=1, small_blind=15, big_blind=30)


@pytest.mark.django_db
def test_blind_structure_levels_are_shared_only_within_a_tournament(pokerok):
    t1 = _make_tournament(pokerok, external_id="a")
    t2 = _make_tournament(pokerok, external_id="b")
    BlindStructure.objects.create(tournament=t1, level=1, small_blind=10, big_blind=20)
    BlindStructure.objects.create(tournament=t2, level=1, small_blind=10, big_blind=20)
    assert BlindStructure.objects.count() == 2


@pytest.mark.django_db
def test_tournament_result_instance_timestamp_is_unique(pokerok):
    tournament = _make_tournament(pokerok)
    started = datetime(2026, 5, 1, 19, 0, tzinfo=UTC)
    TournamentResult.objects.create(
        tournament=tournament, instance_started_at=started, entrants=120
    )
    with pytest.raises(IntegrityError):
        TournamentResult.objects.create(
            tournament=tournament, instance_started_at=started, entrants=150
        )


@pytest.mark.django_db
def test_deleting_tournament_cascades_to_children(pokerok):
    tournament = _make_tournament(pokerok)
    BlindStructure.objects.create(tournament=tournament, level=1, small_blind=10, big_blind=20)
    TournamentResult.objects.create(
        tournament=tournament,
        instance_started_at=datetime(2026, 5, 1, 19, 0, tzinfo=UTC),
        entrants=100,
    )
    tournament.delete()
    assert BlindStructure.objects.count() == 0
    assert TournamentResult.objects.count() == 0
