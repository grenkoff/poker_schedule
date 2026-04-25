"""Tests for the role-change audit log."""

from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, RequestFactory

from apps.users.audit_context import (
    clear_current_request,
    client_ip_from,
    set_current_request,
)
from apps.users.models import AuditSource, Role, RoleChangeAudit

User = get_user_model()


@pytest.fixture(autouse=True)
def _clear_audit_ctx():
    yield
    clear_current_request()


# --- signal-driven creation ----------------------------------------------


@pytest.mark.django_db
def test_user_creation_writes_audit_row():
    u = User.objects.create_user(username="bob", email="bob@example.com", password="x")
    audits = RoleChangeAudit.objects.filter(user=u)
    assert audits.count() == 1
    audit = audits.get()
    assert audit.old_role == ""
    assert audit.new_role == Role.USER


@pytest.mark.django_db
def test_role_change_writes_one_row_per_change():
    u = User.objects.create_user(username="bob", email="bob@example.com", password="x")
    u.role = Role.ADMIN
    u.save()
    u.role = Role.SUPERADMIN
    u.save()
    audits = list(RoleChangeAudit.objects.filter(user=u).order_by("changed_at"))
    assert len(audits) == 3  # create + 2 changes
    assert audits[0].new_role == Role.USER
    assert audits[1].old_role == Role.USER and audits[1].new_role == Role.ADMIN
    assert audits[2].old_role == Role.ADMIN and audits[2].new_role == Role.SUPERADMIN


@pytest.mark.django_db
def test_no_audit_when_save_does_not_change_role():
    u = User.objects.create_user(username="bob", email="bob@example.com", password="x")
    initial = RoleChangeAudit.objects.filter(user=u).count()
    u.timezone = "Europe/Moscow"  # unrelated change
    u.save()
    assert RoleChangeAudit.objects.filter(user=u).count() == initial


# --- request context capture ---------------------------------------------


@pytest.mark.django_db
def test_audit_records_actor_ip_user_agent_from_request():
    actor = User.objects.create_user(
        username="actor",
        email="actor@example.com",
        password="x",
        role=Role.SUPERADMIN,
    )
    rf = RequestFactory()
    request = rf.post(
        "/admin/users/user/2/change/",
        HTTP_USER_AGENT="Mozilla/5.0 TestAgent",
        HTTP_X_FORWARDED_FOR="203.0.113.42",
    )
    request.user = actor
    set_current_request(request)

    target = User.objects.create_user(username="target", email="target@example.com", password="x")
    target.role = Role.ADMIN
    target.save()

    audit = RoleChangeAudit.objects.filter(user=target, new_role=Role.ADMIN).get()
    assert audit.changed_by == actor
    assert audit.ip_address == "203.0.113.42"
    assert audit.user_agent == "Mozilla/5.0 TestAgent"
    assert audit.source == AuditSource.ADMIN


@pytest.mark.django_db
def test_audit_source_is_cli_when_no_request_context():
    User.objects.create_user(username="bob", email="bob@example.com", password="x")
    audit = RoleChangeAudit.objects.latest("changed_at")
    assert audit.source == AuditSource.CLI
    assert audit.ip_address is None
    assert audit.changed_by is None


@pytest.mark.django_db
def test_audit_source_signup_for_non_admin_request():
    rf = RequestFactory()
    request = rf.post("/en/accounts/signup/")
    request.user = type("Anon", (), {"is_authenticated": False})()
    set_current_request(request)

    User.objects.create_user(username="signed", email="signed@example.com", password="x")
    audit = RoleChangeAudit.objects.latest("changed_at")
    assert audit.source == AuditSource.SIGNUP


# --- ip extraction --------------------------------------------------------


def test_client_ip_from_xff_takes_first_entry():
    rf = RequestFactory()
    request = rf.get("/", HTTP_X_FORWARDED_FOR="203.0.113.42, 198.51.100.1")
    assert client_ip_from(request) == "203.0.113.42"


def test_client_ip_from_remote_addr_fallback():
    rf = RequestFactory()
    request = rf.get("/", REMOTE_ADDR="198.51.100.7")
    assert client_ip_from(request) == "198.51.100.7"


def test_client_ip_from_returns_none_without_request():
    assert client_ip_from(None) is None


# --- promote_to_superadmin CLI writes audit ------------------------------


@pytest.mark.django_db
def test_recovery_cli_writes_audit_row():
    User.objects.create_user(username="bob", email="bob@example.com", password="x")
    pre = RoleChangeAudit.objects.filter(new_role=Role.SUPERADMIN).count()
    call_command("promote_to_superadmin", "bob", stdout=StringIO())
    post = RoleChangeAudit.objects.filter(new_role=Role.SUPERADMIN).count()
    assert post == pre + 1
    audit = RoleChangeAudit.objects.filter(new_role=Role.SUPERADMIN).latest("changed_at")
    assert audit.source == AuditSource.CLI


# --- admin gates ----------------------------------------------------------


@pytest.mark.django_db
def test_audit_admin_visible_to_superadmin_and_readonly(client: Client):
    sa = User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    client.force_login(sa)
    response = client.get("/admin/users/rolechangeaudit/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_audit_admin_hidden_from_admin_role(client: Client):
    User.objects.create_user(
        username="admin1", email="admin1@example.com", password="x", role=Role.ADMIN
    )
    client.force_login(User.objects.get(username="admin1"))
    response = client.get("/admin/users/rolechangeaudit/")
    # SuperuserOnlyAdminMixin blocks → admin redirects to login.
    assert response.status_code in (302, 403)


@pytest.mark.django_db
def test_audit_admin_blocks_add_change_delete():
    from apps.users.admin import RoleChangeAuditAdmin

    a = RoleChangeAuditAdmin(RoleChangeAudit, None)
    assert a.has_add_permission(request=None) is False
    assert a.has_change_permission(request=None, obj=None) is False
    assert a.has_delete_permission(request=None, obj=None) is False
