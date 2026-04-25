"""Admin smoke tests: every registered model's changelist, add and change
pages render for a superuser, and the custom actions on Tournament flip
the verified flag."""

from datetime import UTC, datetime

import pytest
from django.contrib.auth import get_user_model

from apps.rooms.models import PokerRoom
from apps.tournaments.models import (
    BlindStructure,
    GameType,
    TableSize,
    Tournament,
    TournamentFormat,
    TournamentResult,
)

User = get_user_model()

# Top-level changelist URLs that should render for a superuser.
# `BlindStructure` and `TournamentResult` are managed only as inlines on
# Tournament; `Group` and `Site` are unused and unregistered — so none of
# them appear here.
ADMIN_URLS = [
    "/admin/users/user/",
    "/admin/rooms/network/",
    "/admin/rooms/pokerroom/",
    "/admin/tournaments/tournament/",
]


@pytest.mark.parametrize("url", ADMIN_URLS)
@pytest.mark.django_db
def test_admin_changelist_renders(admin_client, url):
    response = admin_client.get(url)
    assert response.status_code == 200


@pytest.mark.parametrize("url", [u + "add/" for u in ADMIN_URLS])
@pytest.mark.django_db
def test_admin_add_page_renders(admin_client, url):
    response = admin_client.get(url)
    assert response.status_code == 200


@pytest.mark.parametrize(
    "url",
    [
        "/admin/tournaments/blindstructure/",
        "/admin/tournaments/tournamentresult/",
        "/admin/auth/group/",
        "/admin/sites/site/",
    ],
)
@pytest.mark.django_db
def test_unregistered_admin_pages_are_404(admin_client, url):
    response = admin_client.get(url)
    assert response.status_code == 404


@pytest.fixture
def tournament_with_children() -> Tournament:
    room = PokerRoom.objects.get(slug="pokerok")
    tournament = Tournament.objects.create(
        room=room,
        external_id="admin-1",
        name="Admin Test Daily",
        game_type=GameType.NLHE,
        tournament_format=TournamentFormat.FREEZEOUT,
        table_size=TableSize.NINE_MAX,
        buy_in_cents=5000,
        rake_cents=500,
        currency="USD",
        start_at=datetime(2026, 6, 1, 20, 0, tzinfo=UTC),
    )
    BlindStructure.objects.create(tournament=tournament, level=1, small_blind=25, big_blind=50)
    TournamentResult.objects.create(
        tournament=tournament,
        instance_started_at=datetime(2026, 6, 1, 20, 0, tzinfo=UTC),
        entrants=88,
    )
    return tournament


@pytest.mark.django_db
def test_tournament_change_page_renders(admin_client, tournament_with_children):
    url = f"/admin/tournaments/tournament/{tournament_with_children.pk}/change/"
    response = admin_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_mark_verified_action(admin_client, tournament_with_children):
    assert tournament_with_children.verified_by_admin is False
    response = admin_client.post(
        "/admin/tournaments/tournament/",
        {
            "action": "mark_verified",
            "_selected_action": [str(tournament_with_children.pk)],
        },
        follow=True,
    )
    assert response.status_code == 200
    tournament_with_children.refresh_from_db()
    assert tournament_with_children.verified_by_admin is True


@pytest.mark.django_db
def test_unmark_verified_action(admin_client, tournament_with_children):
    tournament_with_children.verified_by_admin = True
    tournament_with_children.save(update_fields=["verified_by_admin"])
    admin_client.post(
        "/admin/tournaments/tournament/",
        {
            "action": "unmark_verified",
            "_selected_action": [str(tournament_with_children.pk)],
        },
        follow=True,
    )
    tournament_with_children.refresh_from_db()
    assert tournament_with_children.verified_by_admin is False
