"""Tests for the permanent-and-singular SUPERADMIN invariant.

The role cannot be assigned to anyone but the first claimer, cannot be
removed once held, and the holder cannot be deleted. Enforcement spans
the model save/delete, the admin form, the createsuperuser CLI, and a
DB-level partial unique constraint.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
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


# --- promote / demote ---------------------------------------------------


@pytest.mark.django_db
def test_promoting_existing_user_to_superadmin_is_rejected():
    _make("first", role=Role.SUPERADMIN)
    second = _make("second")

    second.role = Role.SUPERADMIN
    with pytest.raises(ValidationError, match="already exists"):
        second.save()

    second.refresh_from_db()
    assert second.role == Role.USER
    assert User.objects.filter(role=Role.SUPERADMIN).count() == 1


@pytest.mark.django_db
def test_creating_new_superadmin_when_one_exists_is_rejected():
    _make("first", role=Role.SUPERADMIN)
    with pytest.raises(ValidationError, match="already exists"):
        _make("second", role=Role.SUPERADMIN)
    assert User.objects.filter(role=Role.SUPERADMIN).count() == 1


@pytest.mark.django_db
def test_superadmin_cannot_demote_themselves():
    sa = _make("sa", role=Role.SUPERADMIN)
    sa.role = Role.ADMIN
    with pytest.raises(ValidationError, match="permanent"):
        sa.save()
    sa.refresh_from_db()
    assert sa.role == Role.SUPERADMIN


@pytest.mark.django_db
def test_superadmin_cannot_become_user_either():
    sa = _make("sa", role=Role.SUPERADMIN)
    sa.role = Role.USER
    with pytest.raises(ValidationError, match="permanent"):
        sa.save()
    sa.refresh_from_db()
    assert sa.role == Role.SUPERADMIN


@pytest.mark.django_db
def test_resaving_superadmin_with_unrelated_changes_is_a_no_op():
    sa = _make("sa", role=Role.SUPERADMIN)
    sa.timezone = "Europe/Moscow"
    sa.preferred_language = "ru"
    sa.save()
    sa.refresh_from_db()
    assert sa.role == Role.SUPERADMIN
    assert sa.timezone == "Europe/Moscow"


@pytest.mark.django_db
def test_first_superadmin_can_be_created_when_none_exists():
    sa = _make("sa", role=Role.SUPERADMIN)
    assert sa.role == Role.SUPERADMIN
    assert sa.is_superuser is True


# --- delete ------------------------------------------------------------


@pytest.mark.django_db
def test_deleting_superadmin_is_blocked_at_model():
    sa = _make("sa", role=Role.SUPERADMIN)
    with pytest.raises(PermissionError, match="permanent"):
        sa.delete()
    assert User.objects.filter(username="sa").exists()


@pytest.mark.django_db
def test_admin_blocks_delete_button_for_superadmin():
    sa = _make("sa", role=Role.SUPERADMIN)
    user_admin = UserAdmin(User, None)
    assert user_admin.has_delete_permission(request=None, obj=sa) is False


@pytest.mark.django_db
def test_admin_allows_delete_button_for_regular_admin():
    class _R:
        user = type("U", (), {"is_active": True, "is_staff": True, "is_superuser": True})()

    _make("sa", role=Role.SUPERADMIN)  # role exists in the system
    other = _make("other", role=Role.ADMIN)
    user_admin = UserAdmin(User, None)
    assert user_admin.has_delete_permission(request=_R(), obj=other) is True


# --- admin form: role field --------------------------------------------


@pytest.mark.django_db
def test_admin_makes_role_readonly_for_superadmin_row():
    sa = _make("sa", role=Role.SUPERADMIN)
    user_admin = UserAdmin(User, None)

    class _R:
        user = type("U", (), {"is_active": True, "is_staff": True, "is_superuser": True})()

    ro = user_admin.get_readonly_fields(request=_R(), obj=sa)
    assert "role" in ro


@pytest.mark.django_db
def test_admin_keeps_role_editable_for_regular_user_row():
    _make("sa", role=Role.SUPERADMIN)
    other = _make("other", role=Role.ADMIN)
    user_admin = UserAdmin(User, None)

    class _R:
        user = type("U", (), {"is_active": True, "is_staff": True, "is_superuser": True})()

    ro = user_admin.get_readonly_fields(request=_R(), obj=other)
    assert "role" not in ro


@pytest.mark.django_db
def test_admin_role_choices_exclude_superadmin_when_one_exists():
    _make("sa", role=Role.SUPERADMIN)
    user_admin = UserAdmin(User, None)
    role_field = User._meta.get_field("role")

    class _R:
        user = type("U", (), {"is_active": True, "is_staff": True, "is_superuser": True})()

    formfield = user_admin.formfield_for_choice_field(role_field, request=_R())
    choice_values = [c[0] for c in formfield.choices]
    assert Role.SUPERADMIN not in choice_values
    assert Role.USER in choice_values
    assert Role.ADMIN in choice_values


@pytest.mark.django_db
def test_admin_role_choices_include_superadmin_when_none_exists():
    """When no SUPERADMIN exists yet, the option is selectable so the
    very first promotion path stays open from the admin too."""
    user_admin = UserAdmin(User, None)
    role_field = User._meta.get_field("role")

    class _R:
        user = type("U", (), {"is_active": True, "is_staff": True, "is_superuser": True})()

    formfield = user_admin.formfield_for_choice_field(role_field, request=_R())
    choice_values = [c[0] for c in formfield.choices]
    assert Role.SUPERADMIN in choice_values


# --- createsuperuser CLI ------------------------------------------------


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


# --- DB constraint -----------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_db_constraint_blocks_two_superadmins_via_raw_update():
    """Application checks live in `save()` and admin form validation;
    the partial unique constraint catches anything that bypasses both."""
    _make("a", role=Role.SUPERADMIN)
    b = _make("b", role=Role.ADMIN)
    with pytest.raises(IntegrityError):
        User.objects.filter(pk=b.pk).update(role=Role.SUPERADMIN)
