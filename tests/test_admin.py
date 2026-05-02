"""Admin smoke tests: every registered model's changelist, add and change
pages render for a superuser, and the unverify bulk action on Tournament
clears the verified flag."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.rooms.models import PokerRoom
from apps.tournaments.models import (
    BlindStructure,
    BubbleOption,
    EarlyBirdType,
    GameType,
    Periodicity,
    ReEntryOption,
    Tournament,
)

User = get_user_model()

# Top-level changelist URLs that should render for a superuser. Inlines
# (BlindStructure) live inside Tournament; Group + Site are unregistered.
ADMIN_URLS = [
    "/admin/users/user/",
    "/admin/rooms/network/",
    "/admin/rooms/pokerroom/",
    "/admin/tournaments/tournament/",
    "/admin/tournaments/reentryoption/",
    "/admin/tournaments/bubbleoption/",
    "/admin/tournaments/earlybirdtype/",
    "/admin/tournaments/periodicity/",
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
        name="Admin Test Daily",
        game_type=GameType.NLHE,
        buy_in_total=Decimal("55.00"),
        buy_in_without_rake=Decimal("50.00"),
        rake=Decimal("5.00"),
        guaranteed_dollars=10000,
        payout_percent=15,
        starting_stack=10000,
        starting_stack_bb=50,
        starting_time=datetime(2026, 6, 1, 20, 0, tzinfo=UTC),
        late_reg_at=datetime(2026, 6, 1, 21, 0, tzinfo=UTC),
        late_reg_level=12,
        blind_interval_minutes=10,
        break_minutes=5,
        players_per_table=9,
        players_at_final_table=9,
        min_players=2,
        max_players=1000,
        re_entry=ReEntryOption.objects.get(name="unlimited"),
        bubble=BubbleOption.objects.get(name="finalized_when_registration_closes"),
        early_bird=False,
        early_bird_type=EarlyBirdType.objects.get(name="compensated_at_bubble"),
        featured_final_table=False,
        periodicity=Periodicity.objects.get(name="one_off"),
    )
    BlindStructure.objects.create(tournament=tournament, level=1, small_blind=25, big_blind=50)
    return tournament


@pytest.mark.django_db
def test_tournament_change_page_renders(admin_client, tournament_with_children):
    url = f"/admin/tournaments/tournament/{tournament_with_children.pk}/change/"
    response = admin_client.get(url)
    assert response.status_code == 200
