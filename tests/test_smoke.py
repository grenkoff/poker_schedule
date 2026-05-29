"""Smoke tests covering the Phase 0 skeleton: healthz, home page."""

import pytest
from django.test import Client


@pytest.fixture
def client() -> Client:
    return Client()


def test_healthz_returns_ok(client: Client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.content == b"ok"


@pytest.mark.django_db
def test_home_renders(client: Client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert b"Poker Schedule" in response.content


@pytest.mark.django_db
def test_admin_login_renders(client: Client) -> None:
    response = client.get("/admin/login/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_accounts_login_renders(client: Client) -> None:
    response = client.get("/accounts/login/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_unknown_path_returns_404(client: Client) -> None:
    response = client.get("/does-not-exist-xyz/")
    assert response.status_code == 404
