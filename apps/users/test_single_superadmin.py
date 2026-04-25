"""Tests for the multi-SUPERADMIN with minimum-1 invariant.

Multiple SUPERADMINs may exist; the system always keeps at least one.
Promotion is unrestricted; demotion or deletion of the last SUPERADMIN
is rejected. createsuperuser always works. The protection lives at the
application layer (matching GitHub-org / Atlassian-site-admin patterns).
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command

from apps.users.admin import UserAdmin
from apps.users.models import Role
from apps.users.models import User as UserModel

User = get_user_model()


def _make(username: str, role: str = Role.USER) -> UserModel:
    return User.objects.create_user(
        username=username, email=f"{username}@example.com", password="x", role=role
    )


# --- promote freely --------------------------------------------------------


@pytest.mark.django_db
def test_can_promote_multiple_users_to_superadmin():
    a = _make("a", role=Role.SUPERADMIN)
    b = _make("b", role=Role.SUPERADMIN)
    assert a.role == Role.SUPERADMIN
    assert b.role == Role.SUPERADMIN
    assert User.objects.filter(role=Role.SUPERADMIN).count() == 2


@pytest.mark.django_db
def test_existing_user_can_be_promoted_to_superadmin():
    _make("first", role=Role.SUPERADMIN)
    second = _make("second")
    second.role = Role.SUPERADMIN
    second.save()
    assert User.objects.filter(role=Role.SUPERADMIN).count() == 2


# --- minimum-1 invariant ---------------------------------------------------


@pytest.mark.django_db
def test_demoting_last_superadmin_is_rejected():
    sa = _make("sa", role=Role.SUPERADMIN)
    sa.role = Role.ADMIN
    with pytest.raises(ValidationError, match="last SUPERADMIN"):
        sa.save()
    sa.refresh_from_db()
    assert sa.role == Role.SUPERADMIN


@pytest.mark.django_db
def test_demoting_a_superadmin_is_ok_when_others_exist():
    a = _make("a", role=Role.SUPERADMIN)
    _make("b", role=Role.SUPERADMIN)
    a.role = Role.ADMIN
    a.save()
    a.refresh_from_db()
    assert a.role == Role.ADMIN
    assert User.objects.filter(role=Role.SUPERADMIN).count() == 1


@pytest.mark.django_db
def test_deleting_last_superadmin_is_rejected():
    sa = _make("sa", role=Role.SUPERADMIN)
    with pytest.raises(PermissionError, match="last SUPERADMIN"):
        sa.delete()
    assert User.objects.filter(username="sa").exists()


@pytest.mark.django_db
def test_deleting_a_superadmin_is_ok_when_others_exist():
    a = _make("a", role=Role.SUPERADMIN)
    _make("b", role=Role.SUPERADMIN)
    a.delete()
    assert not User.objects.filter(username="a").exists()
    assert User.objects.filter(role=Role.SUPERADMIN).count() == 1


# --- createsuperuser CLI ---------------------------------------------------


@pytest.mark.django_db
def test_createsuperuser_works_when_one_already_exists():
    """No more "already exists" failure — multi-SUPERADMIN is supported."""
    _make("first", role=Role.SUPERADMIN)
    call_command(
        "createsuperuser",
        "--noinput",
        "--username=second",
        "--email=second@example.com",
        stdout=StringIO(),
    )
    second = User.objects.get(username="second")
    assert second.role == Role.SUPERADMIN
    assert User.objects.filter(role=Role.SUPERADMIN).count() == 2


# --- admin gates -----------------------------------------------------------


@pytest.mark.django_db
def test_admin_blocks_delete_button_for_last_superadmin():
    sa = _make("sa", role=Role.SUPERADMIN)
    user_admin = UserAdmin(User, None)
    assert user_admin.has_delete_permission(request=None, obj=sa) is False


@pytest.mark.django_db
def test_admin_allows_delete_button_when_other_superadmin_exists():
    class _R:
        user = type("U", (), {"is_active": True, "is_staff": True, "is_superuser": True})()

    a = _make("a", role=Role.SUPERADMIN)
    _make("b", role=Role.SUPERADMIN)
    user_admin = UserAdmin(User, None)
    assert user_admin.has_delete_permission(request=_R(), obj=a) is True


@pytest.mark.django_db
def test_admin_allows_delete_button_for_regular_admin():
    class _R:
        user = type("U", (), {"is_active": True, "is_staff": True, "is_superuser": True})()

    _make("sa", role=Role.SUPERADMIN)
    other = _make("other", role=Role.ADMIN)
    user_admin = UserAdmin(User, None)
    assert user_admin.has_delete_permission(request=_R(), obj=other) is True


# --- non-role saves stay frictionless --------------------------------------


@pytest.mark.django_db
def test_resaving_superadmin_with_unrelated_changes_is_a_no_op():
    sa = _make("sa", role=Role.SUPERADMIN)
    sa.timezone = "Europe/Moscow"
    sa.preferred_language = "ru"
    sa.save()
    sa.refresh_from_db()
    assert sa.role == Role.SUPERADMIN
