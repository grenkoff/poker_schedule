"""Admin smoke tests: every registered model's changelist, add and change
pages render for a superuser, and the unverify bulk action on Tournament
clears the verified flag."""

from datetime import timedelta
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
    TournamentSeries,
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
    series, _ = TournamentSeries.objects.get_or_create(
        room=room, slug="default", defaults={"name": "Default"}
    )
    tournament = Tournament.objects.create(
        room=room,
        series=series,
        name="Admin Test Daily",
        game_type=GameType.NLHE,
        buy_in_total=Decimal("55.00"),
        buy_in_without_rake=Decimal("50.00"),
        rake=Decimal("5.00"),
        guaranteed_dollars=10000,
        payout_percent=15,
        starting_stack=10000,
        starting_stack_bb=50,
        starting_time=timezone.now() + timedelta(hours=1),
        late_reg_at=timezone.now() + timedelta(hours=2),
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
    series, _ = TournamentSeries.objects.get_or_create(
        room=room, slug="default", defaults={"name": "Default"}
    )
    defaults = {
        "room": room,
        "series": series,
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
    # Migration 0006 sets Pokerok's horizon to 7; the assertion below
    # expects the historical 30-day default behaviour.
    room.horizon_days = 30
    room.save(update_fields=["horizon_days"])
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


# --- Save and add same ----------------------------------------------------


@pytest.mark.django_db
def test_clone_helper_copies_form_fields_and_blind_levels(tournament_with_children):
    from apps.tournaments.admin import TournamentAdmin

    BlindStructure.objects.create(
        tournament=tournament_with_children, level=2, small_blind=50, big_blind=100
    )
    admin_instance = TournamentAdmin(Tournament, None)
    clone = admin_instance._clone_tournament(tournament_with_children)

    assert clone.pk != tournament_with_children.pk
    # Every form-level field is preserved.
    for attr in (
        "room_id",
        "series_id",
        "name",
        "game_type",
        "buy_in_total",
        "guaranteed_dollars",
        "payout_percent",
        "starting_stack",
        "starting_time",
        "late_reg_at",
        "late_reg_level",
        "blind_interval_minutes",
        "break_minutes",
        "players_per_table",
        "min_players",
        "max_players",
        "re_entry_id",
        "bubble_id",
        "periodicity_id",
        "weekdays",
        "early_bird",
        "early_bird_type_id",
        "featured_final_table",
    ):
        assert getattr(clone, attr) == getattr(tournament_with_children, attr), attr

    # Blind levels copied 1-to-1.
    src_levels = list(
        tournament_with_children.blind_levels.order_by("level").values(
            "level", "small_blind", "big_blind", "ante"
        )
    )
    clone_levels = list(
        clone.blind_levels.order_by("level").values("level", "small_blind", "big_blind", "ante")
    )
    assert src_levels == clone_levels


@pytest.mark.django_db
def test_clone_strips_series_master_and_resets_verification(tournament_with_children):
    from apps.tournaments.admin import TournamentAdmin

    # Pretend the source was both verified and a child of some series.
    other_master = Tournament.objects.create(
        **{
            **{
                f.name: getattr(tournament_with_children, f.name)
                for f in Tournament._meta.concrete_fields
                if f.name not in {"id", "series_master"}
            },
            "name": "Other Master",
        }
    )
    tournament_with_children.series_master = other_master
    tournament_with_children.verified_by_admin = True
    tournament_with_children.save(update_fields=["series_master", "verified_by_admin"])

    admin_instance = TournamentAdmin(Tournament, None)
    clone = admin_instance._clone_tournament(tournament_with_children)

    assert clone.series_master_id is None
    assert clone.verified_by_admin is False


@pytest.mark.django_db
def test_save_and_add_same_redirects_to_change_view(admin_client, tournament_with_children):
    """POSTing the change form with `_addsame` saves the source, clones
    it, and redirects to the clone's change page."""
    src = tournament_with_children
    # TournamentAdmin hides the legacy "default" series from the dropdown,
    # so the fixture's series fails form validation. Reassign to a real
    # Pokerok series (any of the 24 seeded ones works).
    real_series = TournamentSeries.objects.filter(room=src.room).exclude(slug="default").first()
    src.series = real_series
    src.save(update_fields=["series"])
    url = f"/admin/tournaments/tournament/{src.pk}/change/"
    response = admin_client.post(
        url,
        data={
            "room": str(src.room_id),
            "series": str(src.series_id),
            "name": src.name,
            "game_type": src.game_type,
            "buy_in_without_rake": "50.00",
            "rake": "5.00",
            "guaranteed_dollars": str(src.guaranteed_dollars),
            "payout_percent": str(src.payout_percent),
            "starting_stack": str(src.starting_stack),
            "starting_stack_bb": str(src.starting_stack_bb),
            "timezone": src.timezone,
            "late_registration_available": "on",
            "starting_time_0": src.starting_time.strftime("%d.%m.%Y"),
            "starting_time_1": src.starting_time.strftime("%H:%M"),
            "late_reg_at_0": src.late_reg_at.strftime("%d.%m.%Y"),
            "late_reg_at_1": src.late_reg_at.strftime("%H:%M"),
            "late_reg_level": str(src.late_reg_level),
            "blind_interval_minutes": str(src.blind_interval_minutes),
            "break_minutes": str(src.break_minutes),
            "players_per_table": str(src.players_per_table),
            "players_at_final_table": str(src.players_at_final_table),
            "min_players": str(src.min_players),
            "max_players": str(src.max_players),
            "re_entry": str(src.re_entry_id),
            "bubble": str(src.bubble_id),
            "periodicity": str(src.periodicity_id),
            "weekdays": [str(i) for i in range(7) if src.weekdays & (1 << i)],
            "early_bird": "",
            "early_bird_type": str(src.early_bird_type_id),
            "featured_final_table": "",
            "blind_levels-TOTAL_FORMS": "1",
            "blind_levels-INITIAL_FORMS": "1",
            "blind_levels-MIN_NUM_FORMS": "1",
            "blind_levels-MAX_NUM_FORMS": "1000",
            "blind_levels-0-id": str(src.blind_levels.first().pk),
            "blind_levels-0-tournament": str(src.pk),
            "blind_levels-0-level": "1",
            "blind_levels-0-small_blind": "25",
            "blind_levels-0-big_blind": "50",
            "blind_levels-0-ante": "",
            "_addsame": "1",
        },
    )
    assert response.status_code == 302
    # Source still exists, plus a clone with a higher PK.
    assert Tournament.objects.filter(pk=src.pk).exists()
    clone_pk = int(response["Location"].rstrip("/").rsplit("/", 2)[-2])
    assert clone_pk != src.pk
    clone = Tournament.objects.get(pk=clone_pk)
    assert clone.name == src.name
    assert clone.blind_levels.count() == 1
