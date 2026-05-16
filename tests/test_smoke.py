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
