"""Tests for the User role enum, flag-sync, and admin permission gates."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

from apps.rooms.models import PokerRoom
from apps.tournaments.models import GameType, TableSize, Tournament, TournamentFormat
from apps.users.models import Role

User = get_user_model()


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.fixture
def pokerok() -> PokerRoom:
    return PokerRoom.objects.get(slug="pokerok")


def _make_tournament(room: PokerRoom, *, external_id: str = "t-1", **extras) -> Tournament:
    defaults = {
        "room": room,
        "external_id": external_id,
        "name": "Test",
        "game_type": GameType.NLHE,
        "tournament_format": TournamentFormat.FREEZEOUT,
        "table_size": TableSize.NINE_MAX,
        "buy_in_cents": 1000,
        "currency": "USD",
        "start_at": datetime.now(UTC) + timedelta(hours=2),
    }
    defaults.update(extras)
    return Tournament.objects.create(**defaults)


# --- Role enum + flag sync -------------------------------------------------


@pytest.mark.django_db
def test_default_role_is_user_on_create():
    u = User.objects.create_user(username="u", email="u@example.com", password="x")
    assert u.role == Role.USER
    assert u.is_staff is False
    assert u.is_superuser is False


@pytest.mark.django_db
def test_admin_role_grants_is_staff_only():
    u = User.objects.create_user(username="a", email="a@example.com", password="x", role=Role.ADMIN)
    assert u.is_staff is True
    assert u.is_superuser is False


@pytest.mark.django_db
def test_superadmin_role_grants_both_flags():
    u = User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    assert u.is_staff is True
    assert u.is_superuser is True


@pytest.mark.django_db
def test_role_transition_promotes_and_demotes_flags():
    u = User.objects.create_user(username="u", email="u@example.com", password="x")
    assert u.is_staff is False

    u.role = Role.ADMIN
    u.save()
    assert u.is_staff is True
    assert u.is_superuser is False

    u.role = Role.SUPERADMIN
    u.save()
    assert u.is_staff is True
    assert u.is_superuser is True

    u.role = Role.USER
    u.save()
    assert u.is_staff is False
    assert u.is_superuser is False


@pytest.mark.django_db
def test_createsuperuser_command_assigns_superadmin_role():
    call_command(
        "createsuperuser",
        "--noinput",
        "--username=cli-super",
        "--email=cli@example.com",
        stdout=StringIO(),
    )
    sa = User.objects.get(username="cli-super")
    assert sa.role == Role.SUPERADMIN
    assert sa.is_staff is True
    assert sa.is_superuser is True


@pytest.mark.django_db
def test_allauth_signup_creates_user_role(client: Client):
    client.post(
        "/en/accounts/signup/",
        {
            "email": "fresh@example.com",
            "password1": "ComplexPass#2026",
            "password2": "ComplexPass#2026",
        },
        follow=True,
    )
    u = User.objects.get(email="fresh@example.com")
    assert u.role == Role.USER
    assert u.is_staff is False


# --- Admin permission gates ------------------------------------------------


@pytest.mark.django_db
def test_admin_role_cannot_view_user_admin(client: Client):
    admin_user = User.objects.create_user(
        username="adm", email="adm@example.com", password="x", role=Role.ADMIN
    )
    client.force_login(admin_user)
    response = client.get("/admin/users/user/")
    # Restricted by SuperuserOnlyAdminMixin → Django redirects to login.
    assert response.status_code in (302, 403)


@pytest.mark.django_db
def test_admin_role_cannot_view_group_admin(client: Client):
    admin_user = User.objects.create_user(
        username="adm", email="adm@example.com", password="x", role=Role.ADMIN
    )
    client.force_login(admin_user)
    response = client.get("/admin/auth/group/")
    assert response.status_code in (302, 403)


@pytest.mark.django_db
def test_superadmin_can_view_user_admin(client: Client):
    sa = User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    client.force_login(sa)
    response = client.get("/admin/users/user/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_role_can_view_tournament_admin(client: Client, pokerok: PokerRoom):
    _make_tournament(pokerok, external_id="t-1")
    admin_user = User.objects.create_user(
        username="adm", email="adm@example.com", password="x", role=Role.ADMIN
    )
    client.force_login(admin_user)
    response = client.get("/admin/tournaments/tournament/")
    assert response.status_code == 200


# --- Verification flow -----------------------------------------------------


@pytest.mark.django_db
def test_admin_role_does_not_see_mark_verified_action(client: Client, pokerok: PokerRoom):
    _make_tournament(pokerok, external_id="t-1")
    admin_user = User.objects.create_user(
        username="adm", email="adm@example.com", password="x", role=Role.ADMIN
    )
    client.force_login(admin_user)
    response = client.get("/admin/tournaments/tournament/")
    body = response.content
    assert b"Submit selected tournaments for review" in body
    assert b"Mark selected tournaments as verified" not in body
    assert b"Remove verification" not in body


@pytest.mark.django_db
def test_superadmin_sees_all_actions(client: Client, pokerok: PokerRoom):
    _make_tournament(pokerok, external_id="t-1")
    sa = User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    client.force_login(sa)
    response = client.get("/admin/tournaments/tournament/")
    body = response.content
    assert b"Submit selected tournaments for review" in body
    assert b"Mark selected tournaments as verified" in body


@pytest.mark.django_db
def test_admin_role_sees_verified_by_admin_as_readonly(client: Client, pokerok: PokerRoom):
    t = _make_tournament(pokerok, external_id="t-1")
    admin_user = User.objects.create_user(
        username="adm", email="adm@example.com", password="x", role=Role.ADMIN
    )
    client.force_login(admin_user)
    response = client.get(f"/admin/tournaments/tournament/{t.pk}/change/")
    assert response.status_code == 200
    # Readonly fields render as a static <div>, not as a form input named
    # `verified_by_admin`. Editable would have `name="verified_by_admin"`.
    assert b'name="verified_by_admin"' not in response.content


@pytest.mark.django_db
def test_superadmin_sees_verified_by_admin_as_editable(client: Client, pokerok: PokerRoom):
    t = _make_tournament(pokerok, external_id="t-1")
    sa = User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    client.force_login(sa)
    response = client.get(f"/admin/tournaments/tournament/{t.pk}/change/")
    assert b'name="verified_by_admin"' in response.content


@pytest.mark.django_db
def test_submit_for_review_action_sets_flag(client: Client, pokerok: PokerRoom):
    t = _make_tournament(pokerok, external_id="t-1")
    admin_user = User.objects.create_user(
        username="adm", email="adm@example.com", password="x", role=Role.ADMIN
    )
    client.force_login(admin_user)
    client.post(
        "/admin/tournaments/tournament/",
        {"action": "submit_for_review", "_selected_action": [str(t.pk)]},
        follow=True,
    )
    t.refresh_from_db()
    assert t.submitted_for_review is True
    assert t.verified_by_admin is False  # superadmin still has to verify


@pytest.mark.django_db
def test_mark_verified_action_clears_pending_flag(client: Client, pokerok: PokerRoom):
    t = _make_tournament(pokerok, external_id="t-1", submitted_for_review=True)
    sa = User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    client.force_login(sa)
    client.post(
        "/admin/tournaments/tournament/",
        {"action": "mark_verified", "_selected_action": [str(t.pk)]},
        follow=True,
    )
    t.refresh_from_db()
    assert t.verified_by_admin is True
    assert t.submitted_for_review is False  # cleared on verification
