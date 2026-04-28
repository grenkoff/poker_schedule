"""Tests for user auth flow, profile page, and timezone middleware."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.rooms.models import PokerRoom
from apps.tournaments.models import (
    BubbleOption,
    EarlyBirdType,
    GameType,
    Periodicity,
    ReEntryOption,
    Tournament,
)

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
    starting_time = datetime.now(UTC).replace(
        hour=19, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)
    Tournament.objects.create(
        room=room,
        name="Evening Event",
        game_type=GameType.NLHE,
        buy_in_total_cents=1100,
        buy_in_without_rake_cents=1000,
        rake_cents=100,
        guaranteed_dollars=10000,
        payout_percent=15,
        starting_stack=10000,
        starting_stack_bb=50,
        starting_time=starting_time,
        late_reg_at=starting_time + timedelta(hours=1),
        late_reg_level=12,
        blind_interval_minutes=10,
        break_minutes=5,
        players_per_table=9,
        players_at_final_table=9,
        min_players=2,
        max_players=1000,
        re_entry=ReEntryOption.objects.get(name="unlimited"),
        bubble=BubbleOption.objects.get(name="finalized_when_registration_closes"),
        early_bird=False,
        early_bird_type=EarlyBirdType.objects.get(name="compensated_at_bubble"),
        featured_final_table=False,
        periodicity=Periodicity.objects.get(name="one_off"),
        verified_by_admin=True,
    )

    response = client.get("/en/")
    body = response.content.decode()
    # Moscow is +03 so 19:00 UTC → 22:00 MSK
    assert "22:00" in body
    assert "MSK" in body


@pytest.mark.django_db
def test_anonymous_user_sees_utc(client: Client):
    room = PokerRoom.objects.get(slug="pokerok")
    starting_time = datetime.now(UTC).replace(
        hour=19, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)
    Tournament.objects.create(
        room=room,
        name="UTC Event",
        game_type=GameType.NLHE,
        buy_in_total_cents=1100,
        buy_in_without_rake_cents=1000,
        rake_cents=100,
        guaranteed_dollars=10000,
        payout_percent=15,
        starting_stack=10000,
        starting_stack_bb=50,
        starting_time=starting_time,
        late_reg_at=starting_time + timedelta(hours=1),
        late_reg_level=12,
        blind_interval_minutes=10,
        break_minutes=5,
        players_per_table=9,
        players_at_final_table=9,
        min_players=2,
        max_players=1000,
        re_entry=ReEntryOption.objects.get(name="unlimited"),
        bubble=BubbleOption.objects.get(name="finalized_when_registration_closes"),
        early_bird=False,
        early_bird_type=EarlyBirdType.objects.get(name="compensated_at_bubble"),
        featured_final_table=False,
        periodicity=Periodicity.objects.get(name="one_off"),
        verified_by_admin=True,
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
