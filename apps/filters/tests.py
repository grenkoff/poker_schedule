"""Tests for the TournamentFilter FilterSet, sort helper, and the view's
HTMX-aware template selection."""

from datetime import UTC, datetime, timedelta

import pytest
from django.test import Client

from apps.filters.filters import TournamentFilter
from apps.filters.sort import (
    DEFAULT_SORT,
    apply_sort,
    parse_sort,
    toggle_value,
)
from apps.rooms.models import PokerRoom
from apps.tournaments.models import (
    BubbleOption,
    EarlyBirdType,
    GameType,
    Periodicity,
    ReEntryOption,
    Tournament,
)


@pytest.fixture
def pokerok() -> PokerRoom:
    return PokerRoom.objects.get(slug="pokerok")


@pytest.fixture
def pokerdom() -> PokerRoom:
    return PokerRoom.objects.get(slug="pokerdom")


def _make(
    room: PokerRoom,
    *,
    name: str = "Test",
    game_type: str = GameType.NLHE,
    buy_in_total_cents: int = 1100,
    buy_in_without_rake_cents: int = 1000,
    rake_cents: int = 100,
    starting_time: datetime | None = None,
    re_entry_name: str = "unlimited",
    early_bird: bool = False,
    featured_final_table: bool = False,
    verified_by_admin: bool = False,
) -> Tournament:
    return Tournament.objects.create(
        room=room,
        name=name,
        game_type=game_type,
        buy_in_total_cents=buy_in_total_cents,
        buy_in_without_rake_cents=buy_in_without_rake_cents,
        rake_cents=rake_cents,
        guaranteed_dollars=10000,
        payout_percent=15,
        starting_stack=10000,
        starting_stack_bb=50,
        starting_time=starting_time or (datetime.now(UTC) + timedelta(hours=1)),
        late_reg_at=(starting_time or datetime.now(UTC) + timedelta(hours=1)) + timedelta(hours=1),
        late_reg_level=12,
        blind_interval_minutes=10,
        break_minutes=5,
        players_per_table=9,
        players_at_final_table=9,
        min_players=2,
        max_players=1000,
        re_entry=ReEntryOption.objects.get(name=re_entry_name),
        bubble=BubbleOption.objects.get(name="finalized_when_registration_closes"),
        early_bird=early_bird,
        early_bird_type=EarlyBirdType.objects.get(name="compensated_at_bubble"),
        featured_final_table=featured_final_table,
        verified_by_admin=verified_by_admin,
        periodicity=Periodicity.objects.get(name="one_off"),
    )


# --- filter: rooms --------------------------------------------------------


@pytest.mark.django_db
def test_filter_by_single_room(pokerok: PokerRoom, pokerdom: PokerRoom):
    _make(pokerok, name="Pokerok Event")
    _make(pokerdom, name="PokerDom Event")
    fs = TournamentFilter({"rooms": [pokerok.pk]}, queryset=Tournament.objects.all())
    names = list(fs.qs.values_list("name", flat=True))
    assert names == ["Pokerok Event"]


@pytest.mark.django_db
def test_filter_by_multiple_rooms_is_union(pokerok: PokerRoom, pokerdom: PokerRoom):
    _make(pokerok, name="A")
    _make(pokerdom, name="B")
    fs = TournamentFilter({"rooms": [pokerok.pk, pokerdom.pk]}, queryset=Tournament.objects.all())
    assert fs.qs.count() == 2


# --- filter: game_type ----------------------------------------------------


@pytest.mark.django_db
def test_filter_by_game_type(pokerok: PokerRoom):
    _make(pokerok, name="NLHE", game_type=GameType.NLHE)
    _make(pokerok, name="PLO", game_type=GameType.PLO)
    _make(pokerok, name="PLO5", game_type=GameType.PLO5)
    fs = TournamentFilter(
        {"game_type": [GameType.PLO, GameType.PLO5]},
        queryset=Tournament.objects.all(),
    )
    assert set(fs.qs.values_list("name", flat=True)) == {"PLO", "PLO5"}


# --- filter: buy-in -------------------------------------------------------


@pytest.mark.django_db
def test_filter_buy_in_min_in_dollars(pokerok: PokerRoom):
    _make(pokerok, name="cheap", buy_in_total_cents=500)
    _make(pokerok, name="mid", buy_in_total_cents=2200)
    _make(pokerok, name="big", buy_in_total_cents=22000)
    fs = TournamentFilter({"buy_in_min": 20}, queryset=Tournament.objects.all())
    assert set(fs.qs.values_list("name", flat=True)) == {"mid", "big"}


@pytest.mark.django_db
def test_filter_buy_in_max_in_dollars(pokerok: PokerRoom):
    _make(pokerok, name="cheap", buy_in_total_cents=500)
    _make(pokerok, name="mid", buy_in_total_cents=2200)
    _make(pokerok, name="big", buy_in_total_cents=22000)
    fs = TournamentFilter({"buy_in_max": 25}, queryset=Tournament.objects.all())
    assert set(fs.qs.values_list("name", flat=True)) == {"cheap", "mid"}


@pytest.mark.django_db
def test_filter_buy_in_range(pokerok: PokerRoom):
    _make(pokerok, name="cheap", buy_in_total_cents=500)
    _make(pokerok, name="mid", buy_in_total_cents=2200)
    _make(pokerok, name="big", buy_in_total_cents=22000)
    fs = TournamentFilter({"buy_in_min": 10, "buy_in_max": 100}, queryset=Tournament.objects.all())
    assert list(fs.qs.values_list("name", flat=True)) == ["mid"]


# --- filter: starting time + boolean flags --------------------------------


@pytest.mark.django_db
def test_filter_by_starting_from(pokerok: PokerRoom):
    now = datetime.now(UTC)
    _make(pokerok, name="early", starting_time=now + timedelta(hours=1))
    _make(pokerok, name="late", starting_time=now + timedelta(hours=6))
    cutoff = (now + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S%z")
    fs = TournamentFilter({"starting_from": cutoff}, queryset=Tournament.objects.all())
    assert list(fs.qs.values_list("name", flat=True)) == ["late"]


@pytest.mark.django_db
def test_filter_by_re_entry(pokerok: PokerRoom):
    _make(pokerok, name="freeze", re_entry_name="none")
    _make(pokerok, name="unl", re_entry_name="unlimited")
    none_pk = ReEntryOption.objects.get(name="none").pk
    fs = TournamentFilter({"re_entry": [none_pk]}, queryset=Tournament.objects.all())
    assert list(fs.qs.values_list("name", flat=True)) == ["freeze"]


@pytest.mark.django_db
def test_filter_by_featured_final_table(pokerok: PokerRoom):
    _make(pokerok, name="featured", featured_final_table=True)
    _make(pokerok, name="regular", featured_final_table=False)
    fs = TournamentFilter({"featured_final_table": True}, queryset=Tournament.objects.all())
    assert list(fs.qs.values_list("name", flat=True)) == ["featured"]


# --- sort helper ----------------------------------------------------------


def test_parse_sort_defaults_on_empty():
    assert parse_sort(None) == (DEFAULT_SORT, False)
    assert parse_sort("") == (DEFAULT_SORT, False)


def test_parse_sort_descending_prefix():
    assert parse_sort("-buy_in") == ("buy_in", True)
    assert parse_sort("buy_in") == ("buy_in", False)


def test_parse_sort_rejects_unknown_key():
    assert parse_sort("DROP TABLE") == (DEFAULT_SORT, False)
    assert parse_sort("password") == (DEFAULT_SORT, False)


def test_toggle_value_transitions():
    assert toggle_value(None, "buy_in") == "buy_in"
    assert toggle_value("starting_time", "buy_in") == "buy_in"
    assert toggle_value("buy_in", "buy_in") == "-buy_in"
    assert toggle_value("-buy_in", "buy_in") == "buy_in"


@pytest.mark.django_db
def test_apply_sort_ascending_and_descending(pokerok: PokerRoom):
    _make(pokerok, name="cheap", buy_in_total_cents=100)
    _make(pokerok, name="mid", buy_in_total_cents=500)
    _make(pokerok, name="big", buy_in_total_cents=1000)
    asc = list(apply_sort(Tournament.objects.all(), "buy_in").values_list("name", flat=True))
    desc = list(apply_sort(Tournament.objects.all(), "-buy_in").values_list("name", flat=True))
    assert asc == ["cheap", "mid", "big"]
    assert desc == ["big", "mid", "cheap"]


# --- view integration: HTMX template selection ---------------------------


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.mark.django_db
def test_htmx_request_returns_partial_template(client: Client, pokerok: PokerRoom):
    _make(pokerok, name="Visible Test")
    full = client.get("/en/")
    partial = client.get("/en/", HTTP_HX_REQUEST="true")
    assert b"<html" in full.content
    assert b"<html" not in partial.content
    assert b"Visible Test" in partial.content


@pytest.mark.django_db
def test_list_view_filters_by_game_type(client: Client, pokerok: PokerRoom):
    _make(pokerok, name="NLHE Event", game_type=GameType.NLHE)
    _make(pokerok, name="PLO Event", game_type=GameType.PLO)
    response = client.get("/en/?game_type=PLO")
    assert b"PLO Event" in response.content
    assert b"NLHE Event" not in response.content


@pytest.mark.django_db
def test_list_view_sort_param_reorders(client: Client, pokerok: PokerRoom):
    base = datetime.now(UTC) + timedelta(hours=1)
    _make(
        pokerok,
        name="Cheap Event",
        buy_in_total_cents=500,
        starting_time=base,
    )
    _make(
        pokerok,
        name="Expensive Event",
        buy_in_total_cents=22000,
        starting_time=base + timedelta(minutes=1),
    )
    response = client.get("/en/?sort=-buy_in")
    body = response.content.decode()
    assert body.index("Expensive Event") < body.index("Cheap Event")
