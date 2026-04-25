"""Tests for the soft 2FA enforcement for SUPERADMINs."""

from __future__ import annotations

import pytest
from allauth.mfa.models import Authenticator
from django.contrib.auth import get_user_model
from django.test import Client

from apps.users.models import Role

User = get_user_model()


@pytest.fixture
def client() -> Client:
    return Client()


def _enable_totp(user) -> Authenticator:
    """Persist a fake TOTP authenticator so `user_has_mfa` returns True.

    We don't care about the actual secret here — only the existence of
    a row keyed to this user determines whether the nag fires.
    """
    return Authenticator.objects.create(
        user=user, type=Authenticator.Type.TOTP, data={"secret": "fake-secret"}
    )


# --- nag fires for un-MFA'd SUPERADMIN -----------------------------------


@pytest.mark.django_db
def test_superadmin_without_mfa_sees_warning(client: Client):
    sa = User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    client.force_login(sa)
    response = client.get("/en/")
    assert response.status_code == 200
    assert b"without 2FA" in response.content
    assert b"set up two-factor" in response.content


@pytest.mark.django_db
def test_warning_links_to_mfa_setup(client: Client):
    sa = User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    client.force_login(sa)
    response = client.get("/en/")
    assert b"/accounts/2fa/" in response.content


# --- silent for everyone else --------------------------------------------


@pytest.mark.django_db
def test_superadmin_with_mfa_sees_no_warning(client: Client):
    sa = User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    _enable_totp(sa)
    client.force_login(sa)
    response = client.get("/en/")
    assert b"without 2FA" not in response.content


@pytest.mark.django_db
def test_admin_role_sees_no_warning(client: Client):
    admin_user = User.objects.create_user(
        username="adm", email="adm@example.com", password="x", role=Role.ADMIN
    )
    client.force_login(admin_user)
    response = client.get("/en/")
    assert b"without 2FA" not in response.content


@pytest.mark.django_db
def test_anonymous_sees_no_warning(client: Client):
    response = client.get("/en/")
    assert b"without 2FA" not in response.content


# --- session de-dup + skip rules -----------------------------------------


@pytest.mark.django_db
def test_warning_only_appears_once_per_session(client: Client):
    sa = User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    client.force_login(sa)
    first = client.get("/en/")
    assert b"without 2FA" in first.content
    second = client.get("/en/")
    assert b"without 2FA" not in second.content


@pytest.mark.django_db
def test_warning_skipped_for_htmx_requests(client: Client):
    sa = User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    client.force_login(sa)
    response = client.get("/en/", HTTP_HX_REQUEST="true")
    assert b"without 2FA" not in response.content
    # And the session flag should NOT be set, so the next non-HTMX request
    # still fires the nag.
    fresh = client.get("/en/")
    assert b"without 2FA" in fresh.content


@pytest.mark.django_db
def test_warning_skipped_on_accounts_paths(client: Client):
    sa = User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    client.force_login(sa)
    # Hit an /accounts/ path — the nag must not fire here so the user
    # can navigate to the MFA setup page without hitting the banner.
    response = client.get("/en/accounts/email/")
    assert b"without 2FA" not in response.content


# --- helper ---------------------------------------------------------------


@pytest.mark.django_db
def test_user_has_mfa_helper():
    from apps.users.mfa_check import user_has_mfa

    sa = User.objects.create_user(
        username="sa", email="sa@example.com", password="x", role=Role.SUPERADMIN
    )
    assert user_has_mfa(sa) is False
    _enable_totp(sa)
    assert user_has_mfa(sa) is True
