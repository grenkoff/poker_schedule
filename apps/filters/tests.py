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
    GameType,
    TableSize,
    Tournament,
    TournamentFormat,
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
    external_id: str,
    name: str = "Test",
    game_type: str = GameType.NLHE,
    tournament_format: str = TournamentFormat.FREEZEOUT,
    table_size: str = TableSize.NINE_MAX,
    buy_in_cents: int = 1000,
    start_at: datetime | None = None,
    **extras,
) -> Tournament:
    return Tournament.objects.create(
        room=room,
        external_id=external_id,
        name=name,
        game_type=game_type,
        tournament_format=tournament_format,
        table_size=table_size,
        buy_in_cents=buy_in_cents,
        start_at=start_at or (datetime.now(UTC) + timedelta(hours=1)),
        **extras,
    )


# --- filter: rooms ---------------------------------------------------------


@pytest.mark.django_db
def test_filter_by_single_room(pokerok: PokerRoom, pokerdom: PokerRoom):
    _make(pokerok, external_id="pok-1", name="Pokerok Event")
    _make(pokerdom, external_id="dom-1", name="PokerDom Event")

    fs = TournamentFilter({"rooms": [pokerok.pk]}, queryset=Tournament.objects.all())
    names = list(fs.qs.values_list("name", flat=True))
    assert names == ["Pokerok Event"]


@pytest.mark.django_db
def test_filter_by_multiple_rooms_is_union(pokerok: PokerRoom, pokerdom: PokerRoom):
    _make(pokerok, external_id="pok-1")
    _make(pokerdom, external_id="dom-1")

    fs = TournamentFilter({"rooms": [pokerok.pk, pokerdom.pk]}, queryset=Tournament.objects.all())
    assert fs.qs.count() == 2


# --- filter: game_type / format / table_size -------------------------------


@pytest.mark.django_db
def test_filter_by_game_type(pokerok: PokerRoom):
    _make(pokerok, external_id="nlhe", game_type=GameType.NLHE)
    _make(pokerok, external_id="plo", game_type=GameType.PLO)
    _make(pokerok, external_id="plo5", game_type=GameType.PLO5)

    fs = TournamentFilter(
        {"game_type": [GameType.PLO, GameType.PLO5]},
        queryset=Tournament.objects.all(),
    )
    assert set(fs.qs.values_list("external_id", flat=True)) == {"plo", "plo5"}


@pytest.mark.django_db
def test_filter_by_tournament_format(pokerok: PokerRoom):
    _make(pokerok, external_id="frz", tournament_format=TournamentFormat.FREEZEOUT)
    _make(pokerok, external_id="pko", tournament_format=TournamentFormat.PKO)

    fs = TournamentFilter(
        {"tournament_format": [TournamentFormat.PKO]},
        queryset=Tournament.objects.all(),
    )
    assert list(fs.qs.values_list("external_id", flat=True)) == ["pko"]


@pytest.mark.django_db
def test_filter_by_table_size(pokerok: PokerRoom):
    _make(pokerok, external_id="9", table_size=TableSize.NINE_MAX)
    _make(pokerok, external_id="6", table_size=TableSize.SIX_MAX)

    fs = TournamentFilter({"table_size": [TableSize.SIX_MAX]}, queryset=Tournament.objects.all())
    assert list(fs.qs.values_list("external_id", flat=True)) == ["6"]


# --- filter: buy-in --------------------------------------------------------


@pytest.mark.django_db
def test_filter_buy_in_min_in_dollars(pokerok: PokerRoom):
    _make(pokerok, external_id="cheap", buy_in_cents=500)  # $5
    _make(pokerok, external_id="mid", buy_in_cents=2200)  # $22
    _make(pokerok, external_id="big", buy_in_cents=22000)  # $220

    fs = TournamentFilter({"buy_in_min": 20}, queryset=Tournament.objects.all())
    assert set(fs.qs.values_list("external_id", flat=True)) == {"mid", "big"}


@pytest.mark.django_db
def test_filter_buy_in_max_in_dollars(pokerok: PokerRoom):
    _make(pokerok, external_id="cheap", buy_in_cents=500)
    _make(pokerok, external_id="mid", buy_in_cents=2200)
    _make(pokerok, external_id="big", buy_in_cents=22000)

    fs = TournamentFilter({"buy_in_max": 25}, queryset=Tournament.objects.all())
    assert set(fs.qs.values_list("external_id", flat=True)) == {"cheap", "mid"}


@pytest.mark.django_db
def test_filter_buy_in_range(pokerok: PokerRoom):
    _make(pokerok, external_id="cheap", buy_in_cents=500)
    _make(pokerok, external_id="mid", buy_in_cents=2200)
    _make(pokerok, external_id="big", buy_in_cents=22000)

    fs = TournamentFilter({"buy_in_min": 10, "buy_in_max": 100}, queryset=Tournament.objects.all())
    assert list(fs.qs.values_list("external_id", flat=True)) == ["mid"]


# --- filter: start window --------------------------------------------------


@pytest.mark.django_db
def test_filter_by_start_from(pokerok: PokerRoom):
    now = datetime.now(UTC)
    _make(pokerok, external_id="early", start_at=now + timedelta(hours=1))
    _make(pokerok, external_id="late", start_at=now + timedelta(hours=6))

    cutoff = (now + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S%z")
    fs = TournamentFilter({"start_from": cutoff}, queryset=Tournament.objects.all())
    assert list(fs.qs.values_list("external_id", flat=True)) == ["late"]


# --- filter: late reg + blind reset ---------------------------------------


@pytest.mark.django_db
def test_filter_min_late_reg(pokerok: PokerRoom):
    _make(pokerok, external_id="short", late_reg_minutes=15)
    _make(pokerok, external_id="long", late_reg_minutes=120)

    fs = TournamentFilter({"late_reg_min": 60}, queryset=Tournament.objects.all())
    assert list(fs.qs.values_list("external_id", flat=True)) == ["long"]


@pytest.mark.django_db
def test_filter_blind_reset_at_final(pokerok: PokerRoom):
    _make(pokerok, external_id="reset", blind_reset_at_final=True)
    _make(pokerok, external_id="no-reset", blind_reset_at_final=False)

    fs = TournamentFilter({"blind_reset_at_final": True}, queryset=Tournament.objects.all())
    assert list(fs.qs.values_list("external_id", flat=True)) == ["reset"]


# --- sort helper -----------------------------------------------------------


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
    # First click on a new column → ascending
    assert toggle_value(None, "buy_in") == "buy_in"
    assert toggle_value("start_at", "buy_in") == "buy_in"
    # Click again on same column → descending
    assert toggle_value("buy_in", "buy_in") == "-buy_in"
    # Click once more → back to ascending (default direction)
    assert toggle_value("-buy_in", "buy_in") == "buy_in"


@pytest.mark.django_db
def test_apply_sort_ascending_and_descending(pokerok: PokerRoom):
    _make(pokerok, external_id="cheap", buy_in_cents=100)
    _make(pokerok, external_id="mid", buy_in_cents=500)
    _make(pokerok, external_id="big", buy_in_cents=1000)

    asc = list(apply_sort(Tournament.objects.all(), "buy_in").values_list("external_id", flat=True))
    desc = list(
        apply_sort(Tournament.objects.all(), "-buy_in").values_list("external_id", flat=True)
    )
    assert asc == ["cheap", "mid", "big"]
    assert desc == ["big", "mid", "cheap"]


# --- view integration: HTMX template selection ----------------------------


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.mark.django_db
def test_htmx_request_returns_partial_template(client: Client, pokerok: PokerRoom):
    _make(pokerok, external_id="x")
    full = client.get("/en/")
    partial = client.get("/en/", HTTP_HX_REQUEST="true")

    assert b"<html" in full.content
    assert b"<html" not in partial.content
    assert b"Test" in partial.content  # payload is present in partial


@pytest.mark.django_db
def test_list_view_filters_by_game_type(client: Client, pokerok: PokerRoom):
    _make(pokerok, external_id="nlhe", name="NLHE Event", game_type=GameType.NLHE)
    _make(pokerok, external_id="plo", name="PLO Event", game_type=GameType.PLO)

    response = client.get("/en/?game_type=PLO")
    assert b"PLO Event" in response.content
    assert b"NLHE Event" not in response.content


@pytest.mark.django_db
def test_list_view_sort_param_reorders(client: Client, pokerok: PokerRoom):
    base = datetime.now(UTC) + timedelta(hours=1)
    _make(
        pokerok,
        external_id="cheap",
        name="Cheap Event",
        buy_in_cents=500,
        start_at=base,
    )
    _make(
        pokerok,
        external_id="expensive",
        name="Expensive Event",
        buy_in_cents=22000,
        start_at=base + timedelta(minutes=1),
    )

    response = client.get("/en/?sort=-buy_in")
    body = response.content.decode()
    assert body.index("Expensive Event") < body.index("Cheap Event")
