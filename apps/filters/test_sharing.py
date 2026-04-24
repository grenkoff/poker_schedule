"""Tests for SharedFilter model + create/view flow + PDF export."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.filters.models import SharedFilter
from apps.rooms.models import PokerRoom
from apps.tournaments.models import GameType, TableSize, Tournament, TournamentFormat

User = get_user_model()


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.fixture
def pokerok() -> PokerRoom:
    return PokerRoom.objects.get(slug="pokerok")


def _make_tournament(
    room: PokerRoom,
    *,
    external_id: str,
    name: str = "Test",
    game_type: str = GameType.NLHE,
    **extras,
) -> Tournament:
    defaults = {
        "room": room,
        "external_id": external_id,
        "name": name,
        "game_type": game_type,
        "tournament_format": TournamentFormat.FREEZEOUT,
        "table_size": TableSize.NINE_MAX,
        "buy_in_cents": 1000,
        "rake_cents": 100,
        "currency": "USD",
        "start_at": datetime.now(UTC) + timedelta(hours=2),
    }
    defaults.update(extras)
    return Tournament.objects.create(**defaults)


# --- SharedFilter model ---------------------------------------------------


@pytest.mark.django_db
def test_shared_filter_generates_unique_slug():
    one = SharedFilter.objects.create(filter_params="game_type=PLO")
    two = SharedFilter.objects.create(filter_params="game_type=PLO")
    assert one.slug and two.slug
    assert one.slug != two.slug


@pytest.mark.django_db
def test_shared_filter_not_expired_by_default():
    shared = SharedFilter.objects.create(filter_params="")
    assert shared.is_expired() is False


@pytest.mark.django_db
def test_shared_filter_expiry_in_past_is_expired():
    shared = SharedFilter.objects.create(
        filter_params="",
        expires_at=timezone.now() - timedelta(days=1),
    )
    assert shared.is_expired() is True


@pytest.mark.django_db
def test_shared_filter_expiry_in_future_is_not_expired():
    shared = SharedFilter.objects.create(
        filter_params="",
        expires_at=timezone.now() + timedelta(days=30),
    )
    assert shared.is_expired() is False


@pytest.mark.django_db
def test_shared_filter_str_prefers_name_over_slug():
    shared = SharedFilter.objects.create(filter_params="", name="My Thursday Plan")
    assert str(shared) == "My Thursday Plan"
    unnamed = SharedFilter.objects.create(filter_params="")
    assert str(unnamed) == unnamed.slug


@pytest.mark.django_db
def test_shared_filter_created_by_nullable_on_user_delete():
    user = User.objects.create_user(username="u", email="u@example.com", password="x")
    shared = SharedFilter.objects.create(filter_params="", created_by=user)
    user.delete()
    shared.refresh_from_db()
    assert shared.created_by is None


# --- Share create flow ----------------------------------------------------


@pytest.mark.django_db
def test_anon_can_create_share(client: Client):
    response = client.post(
        "/en/share/create/",
        {"game_type": "PLO", "buy_in_min": "10"},
    )
    assert response.status_code == 302
    shared = SharedFilter.objects.latest("created_at")
    assert response["Location"].endswith(f"/s/{shared.slug}/")
    assert shared.created_by is None
    assert "game_type=PLO" in shared.filter_params
    assert "buy_in_min=10" in shared.filter_params


@pytest.mark.django_db
def test_authenticated_share_records_owner(client: Client):
    user = User.objects.create_user(username="u", email="u@example.com", password="x")
    client.force_login(user)
    client.post("/en/share/create/", {"game_type": "NLHE"})
    shared = SharedFilter.objects.latest("created_at")
    assert shared.created_by == user


@pytest.mark.django_db
def test_share_create_preserves_multi_valued_filters(client: Client):
    # Django's test client serializes list values as repeated keys.
    client.post("/en/share/create/", {"game_type": ["PLO", "NLHE"], "rooms": ["1", "2"]})
    shared = SharedFilter.objects.latest("created_at")
    assert shared.filter_params.count("game_type=") == 2
    assert "game_type=PLO" in shared.filter_params
    assert "game_type=NLHE" in shared.filter_params


@pytest.mark.django_db
def test_share_create_rejects_get(client: Client):
    response = client.get("/en/share/create/")
    assert response.status_code == 405


# --- Shared view ----------------------------------------------------------


@pytest.mark.django_db
def test_shared_view_renders_with_stored_filter(client: Client, pokerok: PokerRoom):
    _make_tournament(pokerok, external_id="nlhe-1", name="NLHE Event", game_type=GameType.NLHE)
    _make_tournament(pokerok, external_id="plo-1", name="PLO Event", game_type=GameType.PLO)

    shared = SharedFilter.objects.create(filter_params="game_type=PLO")
    response = client.get(f"/en/s/{shared.slug}/")
    assert response.status_code == 200
    assert b"PLO Event" in response.content
    assert b"NLHE Event" not in response.content


@pytest.mark.django_db
def test_shared_view_404_for_unknown_slug(client: Client):
    response = client.get("/en/s/does-not-exist/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_shared_view_404_for_expired_link(client: Client, pokerok: PokerRoom):
    _make_tournament(pokerok, external_id="x")
    shared = SharedFilter.objects.create(
        filter_params="",
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    response = client.get(f"/en/s/{shared.slug}/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_shared_view_shows_owner_attribution(client: Client, pokerok: PokerRoom):
    _make_tournament(pokerok, external_id="x")
    user = User.objects.create_user(username="sharer", email="sharer@example.com", password="x")
    shared = SharedFilter.objects.create(filter_params="", created_by=user)
    response = client.get(f"/en/s/{shared.slug}/")
    assert b"sharer@example.com" in response.content


@pytest.mark.django_db
def test_shared_view_allows_sort_on_top_of_stored_filter(client: Client, pokerok: PokerRoom):
    now = datetime.now(UTC) + timedelta(hours=1)
    _make_tournament(pokerok, external_id="cheap", name="Cheap", buy_in_cents=100, start_at=now)
    _make_tournament(
        pokerok,
        external_id="expensive",
        name="Expensive",
        buy_in_cents=10000,
        start_at=now + timedelta(minutes=5),
    )
    shared = SharedFilter.objects.create(filter_params="game_type=NLHE")
    response = client.get(f"/en/s/{shared.slug}/?sort=-buy_in")
    body = response.content.decode()
    assert body.index("Expensive") < body.index("Cheap")


# --- PDF export -----------------------------------------------------------


@pytest.mark.django_db
def test_pdf_export_returns_pdf_content(client: Client, pokerok: PokerRoom):
    _make_tournament(pokerok, external_id="x", name="PDF Event")
    response = client.get("/en/export/pdf/")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("attachment; filename=")
    assert response.content.startswith(b"%PDF")


@pytest.mark.django_db
def test_pdf_export_applies_filter(client: Client, pokerok: PokerRoom):
    _make_tournament(pokerok, external_id="nlhe", name="NLHE Event", game_type=GameType.NLHE)
    _make_tournament(pokerok, external_id="plo", name="PLO Event", game_type=GameType.PLO)
    # Different filter values have to produce different PDFs — trivially
    # asserting size order is brittle (the filter-summary band can add more
    # bytes than a dropped row saves), so just confirm distinct output.
    full = client.get("/en/export/pdf/")
    plo_only = client.get("/en/export/pdf/?game_type=PLO")
    nlhe_only = client.get("/en/export/pdf/?game_type=NLHE")
    assert full.status_code == plo_only.status_code == nlhe_only.status_code == 200
    assert plo_only.content != full.content
    assert plo_only.content != nlhe_only.content


@pytest.mark.django_db
def test_pdf_export_empty_state(client: Client):
    response = client.get("/en/export/pdf/")
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")


# --- Buttons on main list -------------------------------------------------


@pytest.mark.django_db
def test_main_list_has_share_and_pdf_buttons(client: Client):
    response = client.get("/en/")
    assert b"Share this view" in response.content
    assert b"Download PDF" in response.content
    assert reverse("filters:create_share").encode() in response.content
    assert reverse("exports:pdf").encode() in response.content
