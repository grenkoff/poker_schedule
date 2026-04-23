"""Smoke tests covering the Phase 0 skeleton: healthz, i18n routing, home page."""

import pytest
from django.test import Client


@pytest.fixture
def client() -> Client:
    return Client()


def test_healthz_returns_ok(client: Client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.content == b"ok"


def test_root_redirects_to_default_language(client: Client) -> None:
    response = client.get("/")
    assert response.status_code == 302
    assert response["Location"].startswith("/en/")


@pytest.mark.django_db
def test_home_renders_in_english(client: Client) -> None:
    response = client.get("/en/")
    assert response.status_code == 200
    assert b"Poker Schedule" in response.content


@pytest.mark.django_db
@pytest.mark.parametrize(
    "lang_prefix",
    ["en", "ru", "es", "pt-br", "de", "fr", "zh-hans", "ja", "ko", "uk"],
)
def test_home_serves_each_locale(client: Client, lang_prefix: str) -> None:
    response = client.get(f"/{lang_prefix}/")
    assert response.status_code == 200
