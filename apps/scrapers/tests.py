"""Tests for the scraper pipeline: DTOs, registry, upsert, Pokerok adapter,
and the `scrape_room` management command."""

from datetime import UTC, datetime
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.rooms.models import PokerRoom
from apps.scrapers.adapters.pokerok import PokerokScraper
from apps.scrapers.base import BaseScraper
from apps.scrapers.dto import BlindLevelDTO, TournamentDTO
from apps.scrapers.registry import _REGISTRY, get_scraper, register, registered_slugs
from apps.scrapers.upsert import upsert_tournaments
from apps.tournaments.models import BlindStructure, SourceKind, Tournament

# --- DTOs ------------------------------------------------------------------


def _base_dto_kwargs() -> dict:
    return dict(
        external_id="t-1",
        name="Test Tournament",
        game_type="NLHE",
        tournament_format="freezeout",
        table_size="9max",
        buy_in_cents=1000,
        start_at=datetime(2026, 5, 1, 19, 0, tzinfo=UTC),
    )


def test_dto_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        TournamentDTO(**{**_base_dto_kwargs(), "start_at": datetime(2026, 5, 1, 19, 0)})


def test_dto_rejects_negative_amounts():
    with pytest.raises(ValueError, match="non-negative"):
        TournamentDTO(**{**_base_dto_kwargs(), "buy_in_cents": -1})


def test_dto_is_hashable_and_frozen():
    dto = TournamentDTO(**_base_dto_kwargs())
    assert hash(dto)  # hashable — needed for set/dict usage by callers
    with pytest.raises(AttributeError):
        dto.name = "changed"


# --- Registry --------------------------------------------------------------


def test_registry_has_pokerok():
    assert "pokerok" in registered_slugs()
    scraper = get_scraper("pokerok")
    assert isinstance(scraper, PokerokScraper)


def test_registry_unknown_slug_raises_with_known_list():
    with pytest.raises(KeyError, match="pokerok"):
        get_scraper("does-not-exist")


def test_registry_rejects_duplicate_registration():
    class FakeScraper(BaseScraper):
        room_slug = "pokerok"  # collides with the real one

        def fetch_schedule(self):
            return []

    with pytest.raises(ValueError, match="Duplicate"):
        register(FakeScraper)
    # Registry untouched: pokerok still points at the real adapter.
    assert _REGISTRY["pokerok"] is PokerokScraper


def test_registry_rejects_missing_slug():
    class NoSlug(BaseScraper):
        room_slug = ""

        def fetch_schedule(self):
            return []

    with pytest.raises(ValueError, match="room_slug"):
        register(NoSlug)


# --- Pokerok adapter -------------------------------------------------------


def test_pokerok_fixture_loads_and_parses():
    dtos = PokerokScraper().fetch_schedule()
    assert len(dtos) == 8
    ids = {d.external_id for d in dtos}
    assert "pok-daily-bounty-525" in ids
    assert "pok-sunday-main-22000" in ids


def test_pokerok_blind_levels_parsed_for_daily_big():
    dtos = PokerokScraper().fetch_schedule()
    daily_big = next(d for d in dtos if d.external_id == "pok-daily-big-2200")
    assert len(daily_big.blind_levels) == 3
    assert daily_big.blind_levels[0] == BlindLevelDTO(
        level=1, small_blind=100, big_blind=200, ante=0, duration_minutes=None
    )


def test_pokerok_mystery_bounty_has_final_table_reset():
    dtos = PokerokScraper().fetch_schedule()
    mb = next(d for d in dtos if d.external_id == "pok-mystery-bounty-1100")
    assert mb.blind_reset_at_final is True
    assert mb.blind_reset_level == 14


# --- Upsert ----------------------------------------------------------------


@pytest.fixture
def pokerok() -> PokerRoom:
    return PokerRoom.objects.get(slug="pokerok")


def _dto(external_id: str, **overrides) -> TournamentDTO:
    kwargs = _base_dto_kwargs()
    kwargs["external_id"] = external_id
    kwargs.update(overrides)
    return TournamentDTO(**kwargs)


@pytest.mark.django_db
def test_upsert_creates_new_tournaments(pokerok):
    stats = upsert_tournaments(pokerok, [_dto("a"), _dto("b")])
    assert stats.created == 2
    assert stats.updated == 0
    assert Tournament.objects.filter(room=pokerok).count() == 2
    assert all(t.source_kind == SourceKind.SCRAPED for t in Tournament.objects.filter(room=pokerok))


@pytest.mark.django_db
def test_upsert_is_idempotent(pokerok):
    upsert_tournaments(pokerok, [_dto("a"), _dto("b")])
    stats = upsert_tournaments(pokerok, [_dto("a"), _dto("b")])
    assert stats.created == 0
    assert stats.updated == 2


@pytest.mark.django_db
def test_upsert_overwrites_changed_fields(pokerok):
    upsert_tournaments(pokerok, [_dto("a", name="Old Name", buy_in_cents=500)])
    upsert_tournaments(pokerok, [_dto("a", name="New Name", buy_in_cents=1500)])
    t = Tournament.objects.get(room=pokerok, external_id="a")
    assert t.name == "New Name"
    assert t.buy_in_cents == 1500


@pytest.mark.django_db
def test_upsert_preserves_admin_verification_flag(pokerok):
    upsert_tournaments(pokerok, [_dto("a")])
    Tournament.objects.filter(room=pokerok, external_id="a").update(verified_by_admin=True)
    upsert_tournaments(pokerok, [_dto("a", name="Updated")])
    t = Tournament.objects.get(room=pokerok, external_id="a")
    assert t.verified_by_admin is True  # re-scraping must not undo admin work


@pytest.mark.django_db
def test_upsert_replaces_blind_levels(pokerok):
    first = _dto(
        "a",
        blind_levels=(
            BlindLevelDTO(level=1, small_blind=50, big_blind=100),
            BlindLevelDTO(level=2, small_blind=75, big_blind=150, ante=15),
        ),
    )
    upsert_tournaments(pokerok, [first])
    t = Tournament.objects.get(room=pokerok, external_id="a")
    assert t.blind_levels.count() == 2

    second = _dto(
        "a",
        blind_levels=(BlindLevelDTO(level=1, small_blind=100, big_blind=200),),
    )
    upsert_tournaments(pokerok, [second])
    t.refresh_from_db()
    assert t.blind_levels.count() == 1
    only = t.blind_levels.get()
    assert only.small_blind == 100 and only.big_blind == 200


@pytest.mark.django_db
def test_upsert_writes_scraped_at_timestamp(pokerok):
    upsert_tournaments(pokerok, [_dto("a")])
    t = Tournament.objects.get(room=pokerok, external_id="a")
    assert t.scraped_at is not None


@pytest.mark.django_db
def test_upsert_full_pokerok_fixture(pokerok):
    stats = upsert_tournaments(pokerok, PokerokScraper().fetch_schedule())
    assert stats.created == 8
    assert Tournament.objects.filter(room=pokerok).count() == 8
    # "pok-daily-big-2200" carries three blind levels; make sure they landed.
    assert BlindStructure.objects.filter(tournament__external_id="pok-daily-big-2200").count() == 3


# --- Management command ----------------------------------------------------


@pytest.mark.django_db
def test_scrape_room_command_real_run():
    out = StringIO()
    call_command("scrape_room", "pokerok", stdout=out)
    output = out.getvalue()
    assert "8 tournament(s) returned" in output
    assert "8 created" in output
    assert Tournament.objects.filter(room__slug="pokerok").count() == 8


@pytest.mark.django_db
def test_scrape_room_command_dry_run_writes_nothing():
    out = StringIO()
    call_command("scrape_room", "pokerok", "--dry-run", stdout=out)
    assert "not writing to db" in out.getvalue().lower()
    assert Tournament.objects.filter(room__slug="pokerok").count() == 0


@pytest.mark.django_db
def test_scrape_room_command_errors_on_unknown_slug():
    with pytest.raises(CommandError, match="No PokerRoom"):
        call_command("scrape_room", "does-not-exist")
