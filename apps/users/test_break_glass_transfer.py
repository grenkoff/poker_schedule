"""Tests for break-glass flag + transfer-with-confirmation admin action."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.users.models import Role

User = get_user_model()


@pytest.fixture
def client() -> Client:
    return Client()


def _make(username, *, role=Role.USER, is_break_glass=False):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="x",
        role=role,
        is_break_glass=is_break_glass,
    )


# --- break-glass flag ----------------------------------------------------


@pytest.mark.django_db
def test_user_defaults_is_break_glass_false():
    u = _make("u")
    assert u.is_break_glass is False


@pytest.mark.django_db
def test_break_glass_user_hidden_from_default_admin_list(client: Client):
    sa = _make("sa", role=Role.SUPERADMIN)
    _make("emergency", role=Role.SUPERADMIN, is_break_glass=True)
    client.force_login(sa)
    response = client.get("/admin/users/user/")
    assert b"sa@example.com" in response.content
    assert b"emergency@example.com" not in response.content


@pytest.mark.django_db
def test_break_glass_user_visible_with_show_all_filter(client: Client):
    sa = _make("sa", role=Role.SUPERADMIN)
    _make("emergency", role=Role.SUPERADMIN, is_break_glass=True)
    client.force_login(sa)
    response = client.get("/admin/users/user/?break_glass=show")
    assert b"emergency@example.com" in response.content


@pytest.mark.django_db
def test_break_glass_only_filter(client: Client):
    sa = _make("sa", role=Role.SUPERADMIN)
    _make("emergency", role=Role.SUPERADMIN, is_break_glass=True)
    client.force_login(sa)
    response = client.get("/admin/users/user/?break_glass=only")
    assert b"emergency@example.com" in response.content
    assert b"sa@example.com" not in response.content


# --- promote-with-confirmation action ------------------------------------


@pytest.mark.django_db
def test_promote_action_renders_confirmation_page(client: Client):
    sa = _make("sa", role=Role.SUPERADMIN)
    target = _make("target", role=Role.ADMIN)
    client.force_login(sa)
    response = client.post(
        "/admin/users/user/",
        {
            "action": "promote_to_superadmin_with_confirmation",
            "_selected_action": [str(target.pk)],
        },
    )
    assert response.status_code == 200
    assert b"Confirm SUPERADMIN promotion" in response.content
    assert b"target" in response.content
    target.refresh_from_db()
    assert target.role == Role.ADMIN  # not yet promoted


@pytest.mark.django_db
def test_promote_action_with_correct_username_promotes(client: Client):
    sa = _make("sa", role=Role.SUPERADMIN)
    target = _make("target", role=Role.ADMIN)
    client.force_login(sa)
    client.post(
        "/admin/users/user/",
        {
            "action": "promote_to_superadmin_with_confirmation",
            "_selected_action": [str(target.pk)],
            "confirm": "yes",
            "confirm_username": "target",
        },
    )
    target.refresh_from_db()
    assert target.role == Role.SUPERADMIN


@pytest.mark.django_db
def test_promote_action_with_wrong_username_keeps_role(client: Client):
    sa = _make("sa", role=Role.SUPERADMIN)
    target = _make("target", role=Role.ADMIN)
    client.force_login(sa)
    response = client.post(
        "/admin/users/user/",
        {
            "action": "promote_to_superadmin_with_confirmation",
            "_selected_action": [str(target.pk)],
            "confirm": "yes",
            "confirm_username": "TYPO",
        },
    )
    assert response.status_code == 200
    assert b"Username doesn" in response.content  # error rendered
    target.refresh_from_db()
    assert target.role == Role.ADMIN


@pytest.mark.django_db
def test_promote_action_requires_exactly_one_user(client: Client):
    sa = _make("sa", role=Role.SUPERADMIN)
    a = _make("a", role=Role.ADMIN)
    b = _make("b", role=Role.ADMIN)
    client.force_login(sa)
    response = client.post(
        "/admin/users/user/?break_glass=show",
        {
            "action": "promote_to_superadmin_with_confirmation",
            "_selected_action": [str(a.pk), str(b.pk)],
        },
        follow=True,
    )
    assert b"Select exactly one user" in response.content


@pytest.mark.django_db
def test_promote_action_noop_for_already_superadmin(client: Client):
    sa = _make("sa", role=Role.SUPERADMIN)
    other = _make("other", role=Role.SUPERADMIN)
    client.force_login(sa)
    response = client.post(
        "/admin/users/user/",
        {
            "action": "promote_to_superadmin_with_confirmation",
            "_selected_action": [str(other.pk)],
        },
        follow=True,
    )
    assert b"already a SUPERADMIN" in response.content


# --- audit log catches the transfer --------------------------------------


@pytest.mark.django_db
def test_transfer_via_admin_writes_audit_row(client: Client):
    from apps.users.models import RoleChangeAudit

    sa = _make("sa", role=Role.SUPERADMIN)
    target = _make("target", role=Role.USER)
    client.force_login(sa)
    client.post(
        "/admin/users/user/",
        {
            "action": "promote_to_superadmin_with_confirmation",
            "_selected_action": [str(target.pk)],
            "confirm": "yes",
            "confirm_username": "target",
        },
    )
    audit = RoleChangeAudit.objects.filter(user=target, new_role=Role.SUPERADMIN).latest(
        "changed_at"
    )
    assert audit.changed_by == sa
    assert audit.source == "admin"
