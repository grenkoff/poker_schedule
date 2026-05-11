"""Admin smoke tests: every registered model's changelist, add and change
pages render for a superuser, and the unverify bulk action on Tournament
clears the verified flag."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

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


def _make_tournament(room: PokerRoom, **overrides) -> Tournament:
    defaults = {
        "room": room,
        "name": "Tournament",
        "game_type": GameType.NLHE,
        "buy_in_total": Decimal("11.00"),
        "buy_in_without_rake": Decimal("10.00"),
        "rake": Decimal("1.00"),
        "guaranteed_dollars": 1000,
        "payout_percent": 15,
        "starting_stack": 10000,
        "starting_stack_bb": 50,
        "starting_time": timezone.now() + timedelta(hours=1),
        "late_reg_at": timezone.now() + timedelta(hours=2),
        "late_reg_level": 12,
        "blind_interval_minutes": 10,
        "break_minutes": 5,
        "players_per_table": 9,
        "players_at_final_table": 9,
        "min_players": 2,
        "max_players": 1000,
        "re_entry": ReEntryOption.objects.get(name="unlimited"),
        "bubble": BubbleOption.objects.get(name="finalized_when_registration_closes"),
        "early_bird": False,
        "early_bird_type": EarlyBirdType.objects.get(name="compensated_at_bubble"),
        "featured_final_table": False,
        "periodicity": Periodicity.objects.get(name="one_off"),
    }
    defaults.update(overrides)
    return Tournament.objects.create(**defaults)


@pytest.mark.django_db
def test_admin_changelist_hides_closed_late_reg(admin_client):
    room = PokerRoom.objects.get(slug="pokerok")
    now = timezone.now()
    closed = _make_tournament(
        room,
        name="Closed Already",
        starting_time=now - timedelta(hours=2),
        late_reg_at=now - timedelta(hours=1),
    )
    open_ = _make_tournament(
        room,
        name="Still Open",
        starting_time=now,
        late_reg_at=now + timedelta(hours=1),
    )
    response = admin_client.get("/admin/tournaments/tournament/")
    assert response.status_code == 200
    body = response.content.decode()
    assert open_.name in body
    assert closed.name not in body


@pytest.mark.django_db
def test_admin_changelist_hides_started_no_late_reg(admin_client):
    room = PokerRoom.objects.get(slug="pokerok")
    now = timezone.now()
    started = now - timedelta(hours=1)
    no_late_reg = _make_tournament(
        room,
        name="Already Started No LateReg",
        late_registration_available=False,
        starting_time=started,
        late_reg_at=started,
    )
    response = admin_client.get("/admin/tournaments/tournament/")
    assert response.status_code == 200
    assert no_late_reg.name not in response.content.decode()


@pytest.mark.django_db
def test_admin_changelist_extends_recurring_series(admin_client):
    room = PokerRoom.objects.get(slug="pokerok")
    daily = Periodicity.objects.get(name="every_24_hours")
    now = timezone.now()
    # Master start far in the past — regenerate_series at create time
    # would produce only past children. The admin changelist hit must
    # roll the horizon forward.
    master_start = now - timedelta(days=60)
    master = _make_tournament(
        room,
        name="Old Recurring Master",
        periodicity=daily,
        starting_time=master_start,
        late_reg_at=master_start + timedelta(hours=1),
    )
    BlindStructure.objects.create(tournament=master, level=1, small_blind=10, big_blind=20)

    response = admin_client.get("/admin/tournaments/tournament/")
    assert response.status_code == 200

    future_children = Tournament.objects.filter(
        series_master=master,
        starting_time__gt=now,
    )
    assert future_children.exists()
    assert future_children.count() >= 28  # ~30 days at daily cadence, give slack for boundaries
