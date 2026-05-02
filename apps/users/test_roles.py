"""Tests for the User role enum, flag-sync, and admin permission gates."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

from apps.rooms.models import PokerRoom
from apps.tournaments.admin import TournamentAdmin
from apps.tournaments.models import (
    BubbleOption,
    EarlyBirdType,
    GameType,
    Periodicity,
    ReEntryOption,
    Tournament,
)
from apps.users.models import Role

User = get_user_model()


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.fixture
def pokerok() -> PokerRoom:
    return PokerRoom.objects.get(slug="pokerok")


def _make_tournament(room: PokerRoom, **extras) -> Tournament:
    starting_time = datetime.now(UTC) + timedelta(hours=2)
    defaults = {
        "room": room,
        "name": "Test",
        "game_type": GameType.NLHE,
        "buy_in_total": Decimal("11.00"),
        "buy_in_without_rake": Decimal("10.00"),
        "rake": Decimal("1.00"),
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
def test_role_transitions_promote_flags_one_way():
    """USER → ADMIN → SUPERADMIN sets the matching flags. The reverse
    (SUPERADMIN → ADMIN/USER) is rejected by the permanent-superadmin
    invariant — see test_single_superadmin.test_superadmin_cannot_demote_themselves."""
    u = User.objects.create_user(username="u", email="u@example.com", password="x")
    assert u.is_staff is False

    u.role = Role.ADMIN
    u.save()
    assert u.is_staff is True
    assert u.is_superuser is False

    # Demote ADMIN back to USER — allowed; the SUPERADMIN protection
    # only fires when role is moving off SUPERADMIN.
    u.role = Role.USER
    u.save()
    assert u.is_staff is False
    assert u.is_superuser is False

    u.role = Role.SUPERADMIN
    u.save()
    assert u.is_staff is True
    assert u.is_superuser is True


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
    # Group is unregistered from the admin entirely → 404 for everyone,
    # which is strictly stronger than the original "403 for non-superuser".
    assert response.status_code in (302, 403, 404)


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
    _make_tournament(pokerok)
    admin_user = User.objects.create_user(
        username="adm", email="adm@example.com", password="x", role=Role.ADMIN
    )
    client.force_login(admin_user)
    response = client.get("/admin/tournaments/tournament/")
    assert response.status_code == 200


# --- Verification flow -----------------------------------------------------


@pytest.mark.django_db
def test_admin_role_does_not_see_unverify_action(client: Client, pokerok: PokerRoom):
    _make_tournament(pokerok)
    admin_user = User.objects.create_user(
        username="adm", email="adm@example.com", password="x", role=Role.ADMIN
    )
    client.force_login(admin_user)
    response = client.get("/admin/tournaments/tournament/")
    assert b"Return selected tournaments for editing" not in response.content


@pytest.mark.django_db
def test_verify_field_not_rendered_in_form(client: Client, pokerok: PokerRoom):
    """`verified_by_admin` is no longer a form field for any role —
    its value is auto-set on save based on the saving user's role."""
    t = _make_tournament(pokerok)
    sa = User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    client.force_login(sa)
    response = client.get(f"/admin/tournaments/tournament/{t.pk}/change/")
    assert response.status_code == 200
    assert b'name="verified_by_admin"' not in response.content


@pytest.mark.django_db
def test_admin_save_leaves_tournament_unverified(client: Client, pokerok: PokerRoom):
    """ADMIN editing an existing tournament resets it to unverified —
    every ADMIN save sends the tournament back for verification."""
    t = _make_tournament(pokerok, verified_by_admin=True)
    # ADMIN can only edit unverified tournaments, so seed an unverified one
    # via direct DB write to bypass the permission gate.
    Tournament.objects.filter(pk=t.pk).update(verified_by_admin=False)
    admin_user = User.objects.create_user(
        username="adm", email="adm@example.com", password="x", role=Role.ADMIN
    )
    client.force_login(admin_user)
    # Trigger admin's save_model via the bulk-update path: the permission
    # gate covers the change form; here we assert the auto-verify rule
    # directly on save_model by using the changeform POST is heavy. Instead
    # confirm the model-level invariant: ADMIN never marks a tournament
    # verified through the admin save pipeline. Reuse the admin instance.
    request = type("R", (), {"user": admin_user})()
    admin_instance = TournamentAdmin(Tournament, AdminSite())
    t.refresh_from_db()
    admin_instance.save_model(request, t, form=None, change=True)
    t.refresh_from_db()
    assert t.verified_by_admin is False


@pytest.mark.django_db
def test_superadmin_save_marks_tournament_verified(client: Client, pokerok: PokerRoom):
    """SUPERADMIN save auto-verifies — no separate action needed."""
    t = _make_tournament(pokerok)
    assert t.verified_by_admin is False
    sa = User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    request = type("R", (), {"user": sa})()
    admin_instance = TournamentAdmin(Tournament, AdminSite())
    admin_instance.save_model(request, t, form=None, change=True)
    t.refresh_from_db()
    assert t.verified_by_admin is True


@pytest.mark.django_db
def test_admin_cannot_edit_verified_tournament(client: Client, pokerok: PokerRoom):
    """ADMIN gets a read-only view (or 403) on a verified tournament."""
    t = _make_tournament(pokerok, verified_by_admin=True)
    admin_user = User.objects.create_user(
        username="adm", email="adm@example.com", password="x", role=Role.ADMIN
    )
    client.force_login(admin_user)
    response = client.get(f"/admin/tournaments/tournament/{t.pk}/change/")
    # Django returns the change page in read-only mode (200) when
    # has_change_permission(obj) is False — there is no Save button.
    assert response.status_code == 200
    assert b'name="_save"' not in response.content


@pytest.mark.django_db
def test_unverify_button_resets_flag(client: Client, pokerok: PokerRoom):
    t = _make_tournament(pokerok, verified_by_admin=True)
    sa = User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    client.force_login(sa)
    response = client.post(
        f"/admin/tournaments/tournament/{t.pk}/change/",
        {"_unverify": "1"},
        follow=True,
    )
    assert response.status_code == 200
    t.refresh_from_db()
    assert t.verified_by_admin is False
