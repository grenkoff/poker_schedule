"""Tests for the one-SUPERADMIN invariant: auto-demote, delete-protection,
createsuperuser guard, DB constraint."""

from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError

from apps.users.admin import UserAdmin
from apps.users.models import Role
from apps.users.models import User as UserModel

User = get_user_model()


def _make(username: str, role: str = Role.USER) -> UserModel:
    return User.objects.create_user(
        username=username, email=f"{username}@example.com", password="x", role=role
    )


# --- auto-demote ----------------------------------------------------------


@pytest.mark.django_db
def test_promoting_user_to_superadmin_demotes_existing_one():
    first = _make("first", role=Role.SUPERADMIN)
    second = _make("second")

    second.role = Role.SUPERADMIN
    second.save()

    first.refresh_from_db()
    second.refresh_from_db()
    assert second.role == Role.SUPERADMIN
    assert first.role == Role.ADMIN
    assert first.is_staff is True
    assert first.is_superuser is False
    assert User.objects.filter(role=Role.SUPERADMIN).count() == 1


@pytest.mark.django_db
def test_resaving_same_superadmin_does_not_demote_self():
    sa = _make("sa", role=Role.SUPERADMIN)
    # Save again — should be a no-op for the role assignment.
    sa.timezone = "Europe/Moscow"
    sa.save()
    sa.refresh_from_db()
    assert sa.role == Role.SUPERADMIN
    assert User.objects.filter(role=Role.SUPERADMIN).count() == 1


@pytest.mark.django_db
def test_creating_superadmin_when_one_exists_demotes_old():
    """Even via .create_user (not .create_superuser), the invariant holds."""
    _make("first", role=Role.SUPERADMIN)
    _make("second", role=Role.SUPERADMIN)
    assert User.objects.filter(role=Role.SUPERADMIN).count() == 1
    assert User.objects.filter(username="first").get().role == Role.ADMIN


# --- delete-protection ----------------------------------------------------


@pytest.mark.django_db
def test_deleting_sole_superadmin_is_blocked_at_model():
    sa = _make("sa", role=Role.SUPERADMIN)
    with pytest.raises(PermissionError, match="Cannot delete the SUPERADMIN"):
        sa.delete()
    assert User.objects.filter(username="sa").exists()


@pytest.mark.django_db
def test_demoted_former_superadmin_can_be_deleted():
    """After promoting someone else, the old SUPERADMIN is now an ADMIN
    and the protection no longer applies."""
    old = _make("old", role=Role.SUPERADMIN)
    _make("new", role=Role.SUPERADMIN)
    old.refresh_from_db()
    assert old.role == Role.ADMIN
    old.delete()
    assert not User.objects.filter(username="old").exists()


@pytest.mark.django_db
def test_admin_blocks_delete_button_for_superadmin():
    sa = _make("sa", role=Role.SUPERADMIN)
    user_admin = UserAdmin(User, None)
    assert user_admin.has_delete_permission(request=None, obj=sa) is False


@pytest.mark.django_db
def test_admin_allows_delete_button_for_regular_admin():
    """A non-SUPERADMIN row must still be deletable from the admin."""

    class _R:
        user = type("U", (), {"is_active": True, "is_staff": True, "is_superuser": True})()

    sa = _make("sa", role=Role.SUPERADMIN)  # SUPERADMIN must exist for staff context
    other = _make("other", role=Role.ADMIN)
    user_admin = UserAdmin(User, None)
    # Pass a request with an is_superuser user so the SuperuserOnlyAdminMixin
    # check upstream doesn't already block.
    assert user_admin.has_delete_permission(request=_R(), obj=other) is True
    assert sa  # silence unused


# --- createsuperuser guard -----------------------------------------------


@pytest.mark.django_db
def test_createsuperuser_fails_when_one_already_exists():
    _make("first", role=Role.SUPERADMIN)
    with pytest.raises(CommandError, match="already exists"):
        call_command(
            "createsuperuser",
            "--noinput",
            "--username=second",
            "--email=second@example.com",
            stdout=StringIO(),
        )
    assert User.objects.filter(username="second").exists() is False


# --- DB constraint --------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_db_constraint_blocks_two_superadmins_via_raw_update():
    """Even if someone bypasses save() with a raw .update(), the partial
    unique constraint catches it."""
    _make("a", role=Role.SUPERADMIN)
    b = _make("b", role=Role.ADMIN)
    with pytest.raises(IntegrityError):
        # This bypasses User.save() entirely.
        User.objects.filter(pk=b.pk).update(role=Role.SUPERADMIN)
