"""Tests for user auth flow, profile page, and timezone middleware."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.rooms.models import PokerRoom
from apps.tournaments.models import GameType, TableSize, Tournament, TournamentFormat

User = get_user_model()


@pytest.fixture
def client() -> Client:
    return Client()


# --- allauth: pages render ------------------------------------------------


@pytest.mark.django_db
def test_signup_page_renders(client: Client):
    response = client.get("/en/accounts/signup/")
    assert response.status_code == 200
    # Allauth's signup form has an email field
    assert b"email" in response.content.lower()


@pytest.mark.django_db
def test_login_page_renders(client: Client):
    response = client.get("/en/accounts/login/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_password_reset_page_renders(client: Client):
    response = client.get("/en/accounts/password/reset/")
    assert response.status_code == 200


# --- allauth: signup + login flow -----------------------------------------


@pytest.mark.django_db
def test_email_based_signup_creates_user(client: Client):
    response = client.post(
        "/en/accounts/signup/",
        {
            "email": "newguy@example.com",
            "password1": "ComplexPass#2026",
            "password2": "ComplexPass#2026",
        },
        follow=True,
    )
    assert response.status_code == 200
    assert User.objects.filter(email="newguy@example.com").exists()


@pytest.mark.django_db
def test_login_with_email(client: Client):
    # allauth hashes passwords via the AdapterLike path; the convenient
    # equivalent is to create a User and let allauth's auth backend
    # authenticate against it.
    user = User.objects.create_user(
        username="logintester",
        email="logintester@example.com",
        password="ComplexPass#2026",
    )
    assert user.email == "logintester@example.com"

    response = client.post(
        "/en/accounts/login/",
        {"login": "logintester@example.com", "password": "ComplexPass#2026"},
        follow=True,
    )
    assert response.status_code == 200
    # After successful login the session carries the auth user id
    assert "_auth_user_id" in client.session


# --- profile page ---------------------------------------------------------


@pytest.mark.django_db
def test_profile_requires_authentication(client: Client):
    response = client.get("/en/profile/")
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_profile_get_for_authenticated_user(client: Client):
    user = User.objects.create_user(username="u1", email="u1@example.com", password="x")
    client.force_login(user)
    response = client.get("/en/profile/")
    assert response.status_code == 200
    assert b"u1@example.com" in response.content


@pytest.mark.django_db
def test_profile_post_updates_timezone_and_language(client: Client):
    user = User.objects.create_user(username="u1", email="u1@example.com", password="x")
    client.force_login(user)
    response = client.post(
        "/en/profile/",
        {"timezone": "Europe/Moscow", "preferred_language": "ru"},
    )
    # Redirects into the user's newly-chosen locale (ru/ prefix, not en/).
    assert response.status_code == 302
    assert response["Location"] == "/ru/profile/"

    user.refresh_from_db()
    assert user.timezone == "Europe/Moscow"
    assert user.preferred_language == "ru"


@pytest.mark.django_db
def test_profile_rejects_invalid_timezone(client: Client):
    user = User.objects.create_user(username="u1", email="u1@example.com", password="x")
    client.force_login(user)
    response = client.post(
        "/en/profile/",
        {"timezone": "Narnia/Lamppost", "preferred_language": "en"},
    )
    assert response.status_code == 200
    assert b"Unknown timezone" in response.content
    user.refresh_from_db()
    assert user.timezone == "UTC"  # default — unchanged


@pytest.mark.django_db
def test_profile_blank_timezone_defaults_to_utc(client: Client):
    user = User.objects.create_user(username="u1", email="u1@example.com", password="x")
    user.timezone = "Europe/Moscow"
    user.save()
    client.force_login(user)
    client.post("/en/profile/", {"timezone": "", "preferred_language": "en"})
    user.refresh_from_db()
    assert user.timezone == "UTC"


# --- timezone middleware --------------------------------------------------


@pytest.mark.django_db
def test_authenticated_user_timezone_is_applied_to_rendered_times(client: Client):
    """A logged-in user with Europe/Moscow (+03) should see 22:00 MSK
    when the tournament is scheduled for 19:00 UTC."""
    user = User.objects.create_user(
        username="mskguy",
        email="msk@example.com",
        password="x",
        timezone="Europe/Moscow",
    )
    client.force_login(user)

    room = PokerRoom.objects.get(slug="pokerok")
    Tournament.objects.create(
        room=room,
        external_id="tz-1",
        name="Evening Event",
        game_type=GameType.NLHE,
        tournament_format=TournamentFormat.FREEZEOUT,
        table_size=TableSize.NINE_MAX,
        buy_in_cents=1000,
        currency="USD",
        # Make the tournament far enough in the future to survive the
        # upcoming-only filter regardless of when the test runs.
        start_at=datetime.now(UTC).replace(hour=19, minute=0, second=0, microsecond=0)
        + timedelta(days=1),
    )

    response = client.get("/en/")
    body = response.content.decode()
    # Moscow is +03 so 19:00 UTC → 22:00 MSK
    assert "22:00" in body
    assert "MSK" in body


@pytest.mark.django_db
def test_anonymous_user_sees_utc(client: Client):
    room = PokerRoom.objects.get(slug="pokerok")
    Tournament.objects.create(
        room=room,
        external_id="tz-2",
        name="UTC Event",
        game_type=GameType.NLHE,
        tournament_format=TournamentFormat.FREEZEOUT,
        table_size=TableSize.NINE_MAX,
        buy_in_cents=1000,
        currency="USD",
        start_at=datetime.now(UTC).replace(hour=19, minute=0, second=0, microsecond=0)
        + timedelta(days=1),
    )
    response = client.get("/en/")
    body = response.content.decode()
    assert "19:00" in body
    assert "UTC" in body


@pytest.mark.django_db
def test_invalid_timezone_does_not_break_page(client: Client):
    """If a user's row has a garbage timezone, the page still renders in UTC."""
    user = User.objects.create_user(
        username="bad",
        email="bad@example.com",
        password="x",
        timezone="Narnia/Lamppost",
    )
    client.force_login(user)
    response = client.get("/en/")
    assert response.status_code == 200


# --- navigation -----------------------------------------------------------


@pytest.mark.django_db
def test_nav_shows_auth_links_for_anonymous(client: Client):
    response = client.get("/en/")
    assert b"Log in" in response.content
    assert b"Sign up" in response.content


@pytest.mark.django_db
def test_nav_shows_user_menu_for_authenticated(client: Client):
    user = User.objects.create_user(username="u", email="u@example.com", password="x")
    client.force_login(user)
    response = client.get("/en/")
    assert b"u@example.com" in response.content
    assert b"Log out" in response.content
    assert b"Sign up" not in response.content
