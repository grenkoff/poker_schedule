"""Tests for `manage.py promote_to_superadmin`."""

from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.users.models import Role

User = get_user_model()


@pytest.mark.django_db
def test_promote_existing_user_by_username():
    User.objects.create_user(username="bob", email="bob@example.com", password="x")
    out = StringIO()
    call_command("promote_to_superadmin", "bob", stdout=out)
    bob = User.objects.get(username="bob")
    assert bob.role == Role.SUPERADMIN
    assert "Promoted 'bob' from user to SUPERADMIN" in out.getvalue()


@pytest.mark.django_db
def test_promote_existing_user_by_email():
    User.objects.create_user(username="alice", email="alice@example.com", password="x")
    call_command("promote_to_superadmin", "alice@example.com", stdout=StringIO())
    assert User.objects.get(username="alice").role == Role.SUPERADMIN


@pytest.mark.django_db
def test_promote_already_superadmin_is_noop():
    User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    out = StringIO()
    call_command("promote_to_superadmin", "sa", stdout=out)
    assert "already a SUPERADMIN" in out.getvalue()


@pytest.mark.django_db
def test_promote_unknown_user_without_create_errors():
    with pytest.raises(CommandError, match="No user"):
        call_command("promote_to_superadmin", "ghost", stdout=StringIO())


@pytest.mark.django_db
def test_create_and_promote_new_user():
    out = StringIO()
    call_command(
        "promote_to_superadmin",
        "newadmin",
        "--create",
        "--email=newadmin@example.com",
        "--password=ComplexPass#2026",
        stdout=out,
    )
    new = User.objects.get(username="newadmin")
    assert new.role == Role.SUPERADMIN
    assert new.email == "newadmin@example.com"
    assert new.check_password("ComplexPass#2026")
    assert "Created SUPERADMIN 'newadmin'" in out.getvalue()


@pytest.mark.django_db
def test_create_and_promote_with_email_identifier_derives_username():
    call_command(
        "promote_to_superadmin",
        "founder@example.com",
        "--create",
        "--password=ComplexPass#2026",
        stdout=StringIO(),
    )
    u = User.objects.get(email="founder@example.com")
    assert u.username == "founder"
    assert u.role == Role.SUPERADMIN


@pytest.mark.django_db
def test_create_without_password_errors_in_non_interactive_mode(monkeypatch):
    """Without --password, the command falls back to getpass; in tests we
    monkey-patch it to return the empty string and assert the error."""
    import apps.users.management.commands.promote_to_superadmin as cmd

    monkeypatch.setattr(cmd.getpass, "getpass", lambda _prompt: "")
    with pytest.raises(CommandError, match="Password is required"):
        call_command(
            "promote_to_superadmin",
            "x",
            "--create",
            "--email=x@example.com",
            stdout=StringIO(),
        )


@pytest.mark.django_db
def test_promote_logs_warning_for_audit(caplog):
    """Every recovery use must show up at WARNING level for post-mortems."""
    User.objects.create_user(username="bob", email="bob@example.com", password="x")
    with caplog.at_level("WARNING", logger="apps.users.recovery"):
        call_command("promote_to_superadmin", "bob", stdout=StringIO())
    assert any("RECOVERY" in r.message and "bob" in r.message for r in caplog.records)
