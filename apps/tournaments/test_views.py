"""Tests for the public tournament-list view and money template filter."""

from datetime import UTC, datetime, timedelta

import pytest
from django.test import Client
from django.urls import reverse

from apps.rooms.models import PokerRoom
from apps.tournaments.models import (
    BubbleOption,
    EarlyBirdType,
    GameType,
    Periodicity,
    ReEntryOption,
    Tournament,
)
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
    room: PokerRoom, *, name: str = "Test", starting_time: datetime, **overrides
) -> Tournament:
    defaults = {
        "room": room,
        "name": name,
        "game_type": GameType.NLHE,
        "buy_in_total_cents": 1100,
        "buy_in_without_rake_cents": 1000,
        "rake_cents": 100,
        "guaranteed_dollars": 10000,
        "payout_percent": 15,
        "starting_stack": 10000,
        "starting_stack_bb": 50,
        "starting_time": starting_time,
        "late_reg_at": starting_time + timedelta(hours=1),
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
        "periodicity": Periodicity.objects.get(name="one_off"),
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
    _make_tournament(pokerok, name="Upcoming Tournament", starting_time=soon)
    response = client.get("/en/")
    assert response.status_code == 200
    assert b"Upcoming Tournament" in response.content
    assert b"Pokerok" in response.content


@pytest.mark.django_db
def test_list_view_hides_past_tournaments(client: Client, pokerok: PokerRoom):
    past = datetime.now(UTC) - timedelta(hours=2)
    _make_tournament(pokerok, name="Yesterday's Event", starting_time=past)
    response = client.get("/en/")
    assert b"Yesterday's Event" not in response.content


@pytest.mark.django_db
def test_list_view_orders_by_starting_time_ascending(client: Client, pokerok: PokerRoom):
    now = datetime.now(UTC)
    _make_tournament(pokerok, name="Later Event", starting_time=now + timedelta(hours=5))
    _make_tournament(pokerok, name="Sooner Event", starting_time=now + timedelta(hours=1))
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
    base = datetime.now(UTC) + timedelta(hours=1)
    for i in range(51):
        _make_tournament(pokerok, name=f"Event {i:03d}", starting_time=base + timedelta(minutes=i))
    page1 = client.get("/en/")
    assert page1.status_code == 200
    assert b"Page 1 of 2" in page1.content

    page2 = client.get("/en/?page=2")
    assert page2.status_code == 200
    assert b"Event 050" in page2.content


@pytest.mark.django_db
def test_list_view_renders_buy_in(client: Client, pokerok: PokerRoom):
    soon = datetime.now(UTC) + timedelta(hours=2)
    _make_tournament(
        pokerok,
        name="$25 Event",
        starting_time=soon,
        buy_in_total_cents=2500,
        buy_in_without_rake_cents=2300,
        rake_cents=200,
    )
    response = client.get("/en/")
    assert b"$25.00" in response.content


@pytest.mark.django_db
def test_list_view_renders_russian_locale(client: Client, pokerok: PokerRoom):
    soon = datetime.now(UTC) + timedelta(hours=2)
    _make_tournament(pokerok, name="RU Event", starting_time=soon)
    response = client.get("/ru/")
    assert response.status_code == 200
    assert b"RU Event" in response.content
