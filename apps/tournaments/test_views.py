"""Tests for the public tournament-list view and money template filter."""

from datetime import UTC, datetime, timedelta

import pytest
from django.test import Client
from django.urls import reverse

from apps.rooms.models import PokerRoom
from apps.tournaments.models import GameType, TableSize, Tournament, TournamentFormat
from apps.tournaments.templatetags.money import money

# --- money filter ----------------------------------------------------------


def test_money_formats_usd_with_dollar_prefix():
    assert money(1050, "USD") == "$10.50"


def test_money_formats_known_symbols():
    assert money(1000, "EUR") == "€10.00"
    assert money(1000, "GBP") == "£10.00"
    assert money(1000, "RUB") == "₽10.00"
    assert money(1000, "JPY") == "¥10.00"


def test_money_falls_back_to_iso_code_for_unknown_currency():
    assert money(1250, "CAD") == "CAD 12.50"


def test_money_uses_thousand_separator():
    assert money(123456789, "USD") == "$1,234,567.89"


def test_money_returns_empty_on_none():
    assert money(None, "USD") == ""


def test_money_is_case_insensitive_for_currency_code():
    assert money(500, "usd") == "$5.00"


# --- list view -------------------------------------------------------------


@pytest.fixture
def pokerok() -> PokerRoom:
    return PokerRoom.objects.get(slug="pokerok")


def _make_tournament(
    room: PokerRoom, *, external_id: str, start_at: datetime, **overrides
) -> Tournament:
    defaults = {
        "room": room,
        "external_id": external_id,
        "name": f"Test {external_id}",
        "game_type": GameType.NLHE,
        "tournament_format": TournamentFormat.FREEZEOUT,
        "table_size": TableSize.NINE_MAX,
        "buy_in_cents": 1000,
        "rake_cents": 100,
        "currency": "USD",
        "start_at": start_at,
    }
    defaults.update(overrides)
    return Tournament.objects.create(**defaults)


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.mark.django_db
def test_list_view_url_resolves():
    assert reverse("tournaments:list") == "/en/"


@pytest.mark.django_db
def test_list_view_shows_upcoming_tournaments(client: Client, pokerok: PokerRoom):
    soon = datetime.now(UTC) + timedelta(hours=2)
    _make_tournament(pokerok, external_id="upcoming-1", start_at=soon, name="Upcoming Tournament")
    response = client.get("/en/")
    assert response.status_code == 200
    assert b"Upcoming Tournament" in response.content
    assert b"Pokerok" in response.content


@pytest.mark.django_db
def test_list_view_hides_past_tournaments(client: Client, pokerok: PokerRoom):
    past = datetime.now(UTC) - timedelta(hours=2)
    _make_tournament(pokerok, external_id="past-1", start_at=past, name="Yesterday's Event")
    response = client.get("/en/")
    assert b"Yesterday's Event" not in response.content


@pytest.mark.django_db
def test_list_view_orders_by_start_at_ascending(client: Client, pokerok: PokerRoom):
    now = datetime.now(UTC)
    _make_tournament(
        pokerok,
        external_id="later",
        start_at=now + timedelta(hours=5),
        name="Later Event",
    )
    _make_tournament(
        pokerok,
        external_id="sooner",
        start_at=now + timedelta(hours=1),
        name="Sooner Event",
    )
    response = client.get("/en/")
    body = response.content.decode()
    assert body.index("Sooner Event") < body.index("Later Event")


@pytest.mark.django_db
def test_list_view_empty_state(client: Client):
    response = client.get("/en/")
    assert response.status_code == 200
    assert b"No upcoming tournaments" in response.content


@pytest.mark.django_db
def test_list_view_paginates(client: Client, pokerok: PokerRoom):
    """With 51 upcoming tournaments, the first page shows 50, the second 1."""
    base = datetime.now(UTC) + timedelta(hours=1)
    for i in range(51):
        _make_tournament(
            pokerok,
            external_id=f"t-{i:03d}",
            start_at=base + timedelta(minutes=i),
            name=f"Event {i:03d}",
        )

    page1 = client.get("/en/")
    assert page1.status_code == 200
    assert page1.content.count(b"<tr>") == 1 + 50  # header row + 50 tournaments
    assert b"Page 1 of 2" in page1.content

    page2 = client.get("/en/?page=2")
    assert page2.status_code == 200
    assert page2.content.count(b"<tr>") == 1 + 1
    assert b"Event 050" in page2.content


@pytest.mark.django_db
def test_list_view_buy_in_rendered_with_currency_symbol(client: Client, pokerok: PokerRoom):
    soon = datetime.now(UTC) + timedelta(hours=2)
    _make_tournament(
        pokerok,
        external_id="eur-event",
        start_at=soon,
        buy_in_cents=2500,
        rake_cents=0,
        currency="EUR",
        name="Euro Event",
    )
    response = client.get("/en/")
    assert b"\xe2\x82\xac25.00" in response.content  # €25.00 in UTF-8


@pytest.mark.django_db
def test_list_view_renders_russian_locale(client: Client, pokerok: PokerRoom):
    soon = datetime.now(UTC) + timedelta(hours=2)
    _make_tournament(pokerok, external_id="ru-1", start_at=soon, name="RU Event")
    response = client.get("/ru/")
    assert response.status_code == 200
    # The canonical English title is in the <title> until we ship translations,
    # but the page does render for a non-English prefix without falling back
    # to a 500 or a raw template error.
    assert b"RU Event" in response.content
