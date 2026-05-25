"""Tests for tournament models: helpers, relations, blind levels."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.rooms.models import PokerRoom
from apps.tournaments.models import (
    BlindLevelTemplate,
    BlindStructure,
    BlindStructureTemplate,
    BubbleOption,
    EarlyBirdType,
    GameType,
    Periodicity,
    ReEntryOption,
    Tournament,
    TournamentSeries,
)
from apps.tournaments.recurrence import (
    HORIZON_DAYS,
    extend_series_to_horizon,
    regenerate_series,
)


@pytest.fixture
def pokerok() -> PokerRoom:
    room = PokerRoom.objects.get(slug="pokerok")
    # Migration `0006_pokerok_horizon_7` ships a 7-day horizon for the
    # real Pokerok room. The existing recurrence tests were written
    # against the 30-day default and use `pokerok` as the canonical
    # fixture, so reset it here. Per-test horizon tests below override
    # to whatever they need.
    if room.horizon_days != 30:
        room.horizon_days = 30
        room.save(update_fields=["horizon_days"])
    return room


def _default_series(room: PokerRoom) -> TournamentSeries:
    series, _ = TournamentSeries.objects.get_or_create(
        room=room, slug="default", defaults={"name": "Default"}
    )
    return series


def _make_tournament(room: PokerRoom, **overrides) -> Tournament:
    defaults = {
        "room": room,
        "series": _default_series(room),
        "name": "Test Tournament",
        "game_type": GameType.NLHE,
        "buy_in_total": Decimal("11.00"),
        "buy_in_without_rake": Decimal("10.00"),
        "rake": Decimal("1.00"),
        "guaranteed_dollars": 10000,
        "payout_percent": 15,
        "starting_stack": 10000,
        "starting_stack_bb": 50,
        "starting_time": datetime(2026, 5, 1, 19, 0, tzinfo=UTC),
        "late_reg_at": datetime(2026, 5, 1, 20, 0, tzinfo=UTC),
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
def test_tournament_str_includes_room_and_name(pokerok):
    tournament = _make_tournament(pokerok, name="Daily $11 Bounty")
    assert str(tournament) == "Pokerok — Daily $11 Bounty"


@pytest.mark.django_db
def test_tournament_money_decimal_properties(pokerok):
    tournament = _make_tournament(
        pokerok,
        buy_in_total=Decimal("11.00"),
        buy_in_without_rake=Decimal("10.00"),
        rake=Decimal("1.00"),
    )
    assert tournament.buy_in_total == Decimal("11.00")
    assert tournament.buy_in_without_rake == Decimal("10.00")
    assert tournament.rake == Decimal("1.00")


@pytest.mark.django_db
def test_tournament_workflow_defaults(pokerok):
    t = _make_tournament(pokerok)
    assert t.verified_by_admin is False


@pytest.mark.django_db
def test_tournament_timezone_default_is_utc(pokerok):
    t = _make_tournament(pokerok)
    assert t.timezone == "UTC"


@pytest.mark.django_db
def test_admin_form_rejects_late_reg_before_start(pokerok):
    from apps.tournaments.forms import TournamentAdminForm

    form = TournamentAdminForm(
        data={
            "room": str(pokerok.pk),
            "series": str(_default_series(pokerok).pk),
            "name": "X",
            "game_type": GameType.NLHE,
            "buy_in_without_rake": "10.00",
            "rake": "1.00",
            "guaranteed_dollars": "100",
            "payout_percent": "15",
            "starting_stack": "10000",
            "starting_stack_bb": "50",
            "timezone": "UTC",
            "late_registration_available": "on",
            "starting_time_0": "01.05.2026",
            "starting_time_1": "20:00",
            "late_reg_at_0": "01.05.2026",
            "late_reg_at_1": "19:30",
            "late_reg_level": "12",
            "blind_interval_minutes": "10",
            "break_minutes": "5",
            "players_per_table": "9",
            "players_at_final_table": "9",
            "min_players": "2",
            "max_players": "1000",
            "re_entry": str(ReEntryOption.objects.get(name="unlimited").pk),
            "bubble": str(BubbleOption.objects.get(name="finalized_when_registration_closes").pk),
            "periodicity": str(Periodicity.objects.get(name="one_off").pk),
            "weekdays": ["0", "1", "2", "3", "4", "5", "6"],
            "early_bird": "",
            "early_bird_type": str(EarlyBirdType.objects.get(name="compensated_at_bubble").pk),
            "featured_final_table": "",
        }
    )
    assert not form.is_valid()
    assert "late_reg_at" in form.errors


@pytest.mark.django_db
def test_admin_form_pins_late_reg_to_start_when_disabled(pokerok):
    from apps.tournaments.forms import TournamentAdminForm

    form = TournamentAdminForm(
        data={
            "room": str(pokerok.pk),
            "series": str(_default_series(pokerok).pk),
            "name": "Z",
            "game_type": GameType.NLHE,
            "buy_in_without_rake": "10.00",
            "rake": "1.00",
            "guaranteed_dollars": "100",
            "payout_percent": "15",
            "starting_stack": "10000",
            "starting_stack_bb": "50",
            "timezone": "UTC",
            # checkbox missing => unchecked
            "starting_time_0": "01.05.2026",
            "starting_time_1": "20:00",
            # Late inputs left blank — clean() should pin them to start.
            "late_reg_at_0": "",
            "late_reg_at_1": "",
            "late_reg_level": "12",
            "blind_interval_minutes": "10",
            "break_minutes": "5",
            "players_per_table": "9",
            "players_at_final_table": "9",
            "min_players": "2",
            "max_players": "1000",
            "re_entry": str(ReEntryOption.objects.get(name="unlimited").pk),
            "bubble": str(BubbleOption.objects.get(name="finalized_when_registration_closes").pk),
            "periodicity": str(Periodicity.objects.get(name="one_off").pk),
            "weekdays": ["0", "1", "2", "3", "4", "5", "6"],
            "early_bird": "",
            "early_bird_type": str(EarlyBirdType.objects.get(name="compensated_at_bubble").pk),
            "featured_final_table": "",
        }
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.late_registration_available is False
    assert saved.late_reg_at == saved.starting_time


@pytest.mark.django_db
def test_admin_form_saves_timezone(pokerok):
    from apps.tournaments.forms import TournamentAdminForm

    form = TournamentAdminForm(
        data={
            "room": str(pokerok.pk),
            "series": str(_default_series(pokerok).pk),
            "name": "TZ Tournament",
            "game_type": GameType.NLHE,
            "buy_in_without_rake": "10.00",
            "rake": "1.00",
            "guaranteed_dollars": "100",
            "payout_percent": "15",
            "starting_stack": "10000",
            "starting_stack_bb": "50",
            "timezone": "Europe/Moscow",
            "late_registration_available": "on",
            "starting_time_0": "01.05.2026",
            "starting_time_1": "19:00",
            "late_reg_at_0": "01.05.2026",
            "late_reg_at_1": "20:00",
            "late_reg_level": "12",
            "blind_interval_minutes": "10",
            "break_minutes": "5",
            "players_per_table": "9",
            "players_at_final_table": "9",
            "min_players": "2",
            "max_players": "1000",
            "re_entry": str(ReEntryOption.objects.get(name="unlimited").pk),
            "bubble": str(BubbleOption.objects.get(name="finalized_when_registration_closes").pk),
            "periodicity": str(Periodicity.objects.get(name="one_off").pk),
            "weekdays": ["0", "1", "2", "3", "4", "5", "6"],
            "early_bird": "",
            "early_bird_type": str(EarlyBirdType.objects.get(name="compensated_at_bubble").pk),
            "featured_final_table": "",
        }
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.timezone == "Europe/Moscow"


@pytest.mark.django_db
def test_blind_level_unique_per_tournament(pokerok):
    tournament = _make_tournament(pokerok)
    BlindStructure.objects.create(tournament=tournament, level=1, small_blind=10, big_blind=20)
    with pytest.raises(IntegrityError):
        BlindStructure.objects.create(tournament=tournament, level=1, small_blind=15, big_blind=30)


@pytest.mark.django_db
def test_blind_levels_independent_across_tournaments(pokerok):
    t1 = _make_tournament(pokerok, name="A")
    t2 = _make_tournament(
        pokerok,
        name="B",
        starting_time=datetime(2026, 5, 1, 19, 0, tzinfo=UTC) + timedelta(hours=1),
    )
    BlindStructure.objects.create(tournament=t1, level=1, small_blind=10, big_blind=20)
    BlindStructure.objects.create(tournament=t2, level=1, small_blind=10, big_blind=20)
    assert BlindStructure.objects.count() == 2


@pytest.mark.django_db
def test_deleting_tournament_cascades_to_blind_levels(pokerok):
    tournament = _make_tournament(pokerok)
    BlindStructure.objects.create(tournament=tournament, level=1, small_blind=10, big_blind=20)
    tournament.delete()
    assert BlindStructure.objects.count() == 0


@pytest.mark.django_db
def test_option_models_seeded():
    """The 0002_seed_options migration plants the defaults."""
    assert ReEntryOption.objects.filter(name="unlimited").exists()
    assert BubbleOption.objects.filter(name="finalized_when_registration_closes").exists()
    assert EarlyBirdType.objects.filter(name="compensated_at_bubble").exists()


@pytest.mark.django_db
def test_periodicity_seeded():
    assert Periodicity.objects.get(name="one_off").interval_seconds == 0
    assert Periodicity.objects.get(name="every_4_hours").interval_seconds == 4 * 3600
    assert Periodicity.objects.get(name="every_24_hours").interval_seconds == 24 * 3600
    assert Periodicity.objects.get(name="weekly").interval_seconds == 7 * 24 * 3600


@pytest.mark.django_db
def test_regenerate_series_one_off_creates_no_children(pokerok):
    master = _make_tournament(pokerok)
    regenerate_series(master)
    assert Tournament.objects.filter(series_master=master).count() == 0


@pytest.mark.django_db
def test_regenerate_series_every_24_hours_within_30_day_horizon(pokerok):
    daily = Periodicity.objects.get(name="every_24_hours")
    master = _make_tournament(pokerok, periodicity=daily)
    BlindStructure.objects.create(tournament=master, level=1, small_blind=10, big_blind=20)
    regenerate_series(master)
    children = Tournament.objects.filter(series_master=master).order_by("starting_time")
    assert children.count() == 30
    assert children.first().starting_time == master.starting_time + timedelta(days=1)
    assert children.last().starting_time == master.starting_time + timedelta(days=30)
    # Blind levels are duplicated to every child.
    for child in children:
        assert child.blind_levels.count() == 1
    # late_reg offset is preserved.
    offset = master.late_reg_at - master.starting_time
    for child in children:
        assert child.late_reg_at - child.starting_time == offset


@pytest.mark.django_db
def test_regenerate_series_is_idempotent(pokerok):
    weekly = Periodicity.objects.get(name="weekly")
    master = _make_tournament(pokerok, periodicity=weekly)
    regenerate_series(master)
    first_count = Tournament.objects.filter(series_master=master).count()
    regenerate_series(master)
    assert Tournament.objects.filter(series_master=master).count() == first_count


@pytest.mark.django_db
def test_regenerate_series_skipped_for_child(pokerok):
    daily = Periodicity.objects.get(name="every_24_hours")
    master = _make_tournament(pokerok, periodicity=daily)
    regenerate_series(master)
    child = Tournament.objects.filter(series_master=master).first()
    # Calling on a child must be a no-op (no grandchildren).
    regenerate_series(child)
    assert Tournament.objects.filter(series_master=child).count() == 0


@pytest.mark.django_db
def test_extend_series_no_op_for_one_off(pokerok):
    master = _make_tournament(pokerok)
    assert extend_series_to_horizon(master) == 0
    assert Tournament.objects.filter(series_master=master).count() == 0


@pytest.mark.django_db
def test_extend_series_is_idempotent(pokerok):
    daily = Periodicity.objects.get(name="every_24_hours")
    now = datetime(2026, 5, 11, 12, 0, tzinfo=UTC)
    master = _make_tournament(
        pokerok,
        periodicity=daily,
        starting_time=now - timedelta(hours=1),
        late_reg_at=now - timedelta(minutes=30),
    )
    regenerate_series(master)
    extend_series_to_horizon(master, now=now)
    first_count = Tournament.objects.filter(series_master=master).count()
    assert extend_series_to_horizon(master, now=now) == 0
    assert Tournament.objects.filter(series_master=master).count() == first_count


@pytest.mark.django_db
def test_extend_series_skipped_for_child(pokerok):
    daily = Periodicity.objects.get(name="every_24_hours")
    master = _make_tournament(pokerok, periodicity=daily)
    regenerate_series(master)
    child = Tournament.objects.filter(series_master=master).first()
    assert extend_series_to_horizon(child) == 0


@pytest.mark.django_db
def test_extend_series_rolls_horizon_forward_for_old_master(pokerok):
    daily = Periodicity.objects.get(name="every_24_hours")
    now = datetime(2026, 5, 11, 12, 0, tzinfo=UTC)
    master_start = now - timedelta(days=60)
    master = _make_tournament(
        pokerok,
        periodicity=daily,
        starting_time=master_start,
        late_reg_at=master_start + timedelta(hours=1),
    )
    BlindStructure.objects.create(tournament=master, level=1, small_blind=10, big_blind=20)
    regenerate_series(master)
    # Initial children all sit in the past (within master_start + 30d).
    initial_children = Tournament.objects.filter(series_master=master).order_by("starting_time")
    assert initial_children.count() == HORIZON_DAYS
    assert all(c.starting_time < now for c in initial_children)

    created = extend_series_to_horizon(master, now=now)
    horizon_end = now + timedelta(days=HORIZON_DAYS)

    children = Tournament.objects.filter(series_master=master).order_by("starting_time")
    # Old children are not deleted by the lazy extender.
    assert children.count() == initial_children.count() + created
    future = [c for c in children if c.starting_time > now]
    assert future, "extender should have produced future occurrences"
    assert all(c.starting_time <= horizon_end for c in future)
    # First future occurrence sits within one period of `now`.
    first_future = future[0]
    assert now - timedelta(days=1) < first_future.starting_time <= now + timedelta(days=1)
    # Blind levels are duplicated to every newly created child.
    for child in future:
        assert child.blind_levels.count() == 1


@pytest.mark.django_db
def test_extend_series_creates_initial_children_when_master_has_none(pokerok):
    daily = Periodicity.objects.get(name="every_24_hours")
    now = datetime(2026, 5, 11, 12, 0, tzinfo=UTC)
    master = _make_tournament(
        pokerok,
        periodicity=daily,
        starting_time=now + timedelta(hours=1),
        late_reg_at=now + timedelta(hours=2),
    )
    # No regenerate_series call: simulate a master with no materialized children.
    assert Tournament.objects.filter(series_master=master).count() == 0
    created = extend_series_to_horizon(master, now=now)
    # Master starts at now+1h, daily cadence: occurrences at +1d+1h, +2d+1h, ...
    # The last one fitting in (now, now+30d] is +29d+1h → 29 children.
    assert created == HORIZON_DAYS - 1
    assert Tournament.objects.filter(series_master=master).count() == HORIZON_DAYS - 1
    horizon_end = now + timedelta(days=HORIZON_DAYS)
    for child in Tournament.objects.filter(series_master=master):
        assert now < child.starting_time <= horizon_end


# --- weekday recurrence filter --------------------------------------------


@pytest.mark.django_db
def test_weekdays_default_is_all_days(pokerok):
    t = _make_tournament(pokerok)
    assert t.weekdays == 0b1111111


@pytest.mark.django_db
def test_regenerate_series_skips_disallowed_weekdays(pokerok):
    daily = Periodicity.objects.get(name="every_24_hours")
    # 2026-05-04 is a Monday. Mask 0b0111111 = all except Sunday (bit 6).
    master = _make_tournament(
        pokerok,
        periodicity=daily,
        starting_time=datetime(2026, 5, 4, 19, 0, tzinfo=UTC),
        late_reg_at=datetime(2026, 5, 4, 20, 0, tzinfo=UTC),
        weekdays=0b0111111,
    )
    regenerate_series(master)
    children = Tournament.objects.filter(series_master=master)
    # Every child's weekday must be in Mon..Sat (0..5), never Sunday (6).
    weekdays_seen = {c.starting_time.weekday() for c in children}
    assert 6 not in weekdays_seen
    # And the count drops by the number of Sundays in the horizon window.
    horizon_dates = [master.starting_time + timedelta(days=d) for d in range(1, HORIZON_DAYS + 1)]
    expected = sum(1 for d in horizon_dates if d.weekday() != 6)
    assert children.count() == expected


@pytest.mark.django_db
def test_admin_form_rejects_starting_time_on_disallowed_weekday(pokerok):
    from apps.tournaments.forms import TournamentAdminForm

    daily = Periodicity.objects.get(name="every_24_hours")
    # 2026-05-03 is a Sunday. Submitting the daily series with Sunday
    # unchecked must fail validation on the `weekdays` field.
    form = TournamentAdminForm(
        data={
            "room": str(pokerok.pk),
            "series": str(_default_series(pokerok).pk),
            "name": "Sunday Daily",
            "game_type": GameType.NLHE,
            "buy_in_without_rake": "10.00",
            "rake": "1.00",
            "guaranteed_dollars": "100",
            "payout_percent": "15",
            "starting_stack": "10000",
            "starting_stack_bb": "50",
            "timezone": "UTC",
            "late_registration_available": "on",
            "starting_time_0": "03.05.2026",
            "starting_time_1": "20:00",
            "late_reg_at_0": "03.05.2026",
            "late_reg_at_1": "20:30",
            "late_reg_level": "12",
            "blind_interval_minutes": "10",
            "break_minutes": "5",
            "players_per_table": "9",
            "players_at_final_table": "9",
            "min_players": "2",
            "max_players": "1000",
            "re_entry": str(ReEntryOption.objects.get(name="unlimited").pk),
            "bubble": str(BubbleOption.objects.get(name="finalized_when_registration_closes").pk),
            "periodicity": str(daily.pk),
            "weekdays": ["0", "1", "2", "3", "4", "5"],  # Sunday unchecked
            "early_bird": "",
            "early_bird_type": str(EarlyBirdType.objects.get(name="compensated_at_bubble").pk),
            "featured_final_table": "",
        }
    )
    assert not form.is_valid()
    assert "weekdays" in form.errors


@pytest.mark.django_db
def test_admin_form_rejects_empty_weekdays_for_recurring(pokerok):
    from apps.tournaments.forms import TournamentAdminForm

    daily = Periodicity.objects.get(name="every_24_hours")
    form = TournamentAdminForm(
        data={
            "room": str(pokerok.pk),
            "series": str(_default_series(pokerok).pk),
            "name": "Empty Mask",
            "game_type": GameType.NLHE,
            "buy_in_without_rake": "10.00",
            "rake": "1.00",
            "guaranteed_dollars": "100",
            "payout_percent": "15",
            "starting_stack": "10000",
            "starting_stack_bb": "50",
            "timezone": "UTC",
            "late_registration_available": "on",
            "starting_time_0": "01.05.2026",
            "starting_time_1": "20:00",
            "late_reg_at_0": "01.05.2026",
            "late_reg_at_1": "20:30",
            "late_reg_level": "12",
            "blind_interval_minutes": "10",
            "break_minutes": "5",
            "players_per_table": "9",
            "players_at_final_table": "9",
            "min_players": "2",
            "max_players": "1000",
            "re_entry": str(ReEntryOption.objects.get(name="unlimited").pk),
            "bubble": str(BubbleOption.objects.get(name="finalized_when_registration_closes").pk),
            "periodicity": str(daily.pk),
            "weekdays": [],
            "early_bird": "",
            "early_bird_type": str(EarlyBirdType.objects.get(name="compensated_at_bubble").pk),
            "featured_final_table": "",
        }
    )
    assert not form.is_valid()
    assert "weekdays" in form.errors


@pytest.mark.django_db
def test_admin_form_accepts_empty_weekdays_for_one_off(pokerok):
    """One-off tournament ignores the mask — empty POST is acceptable and
    the saved row falls back to the all-days default."""
    from apps.tournaments.forms import TournamentAdminForm

    form = TournamentAdminForm(
        data={
            "room": str(pokerok.pk),
            "series": str(_default_series(pokerok).pk),
            "name": "One-off",
            "game_type": GameType.NLHE,
            "buy_in_without_rake": "10.00",
            "rake": "1.00",
            "guaranteed_dollars": "100",
            "payout_percent": "15",
            "starting_stack": "10000",
            "starting_stack_bb": "50",
            "timezone": "UTC",
            "late_registration_available": "on",
            "starting_time_0": "01.05.2026",
            "starting_time_1": "20:00",
            "late_reg_at_0": "01.05.2026",
            "late_reg_at_1": "20:30",
            "late_reg_level": "12",
            "blind_interval_minutes": "10",
            "break_minutes": "5",
            "players_per_table": "9",
            "players_at_final_table": "9",
            "min_players": "2",
            "max_players": "1000",
            "re_entry": str(ReEntryOption.objects.get(name="unlimited").pk),
            "bubble": str(BubbleOption.objects.get(name="finalized_when_registration_closes").pk),
            "periodicity": str(Periodicity.objects.get(name="one_off").pk),
            "weekdays": [],
            "early_bird": "",
            "early_bird_type": str(EarlyBirdType.objects.get(name="compensated_at_bubble").pk),
            "featured_final_table": "",
        }
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.weekdays == 0b1111111


@pytest.mark.django_db
def test_one_off_ignores_weekdays_mask(pokerok):
    # A one-off has interval_seconds=0 → regenerate_series is a no-op
    # before weekday filtering runs, so any mask is benign.
    master = _make_tournament(pokerok, weekdays=0b0000001)  # Monday only
    regenerate_series(master)
    assert Tournament.objects.filter(series_master=master).count() == 0


# --- tournament series ----------------------------------------------------


@pytest.mark.django_db
def test_admin_form_rejects_series_from_different_room(pokerok):
    from apps.tournaments.forms import TournamentAdminForm

    other_room = PokerRoom.objects.exclude(pk=pokerok.pk).first()
    assert other_room is not None
    foreign_series = TournamentSeries.objects.create(
        room=other_room, name="Foreign", slug="foreign"
    )
    form = TournamentAdminForm(
        data={
            "room": str(pokerok.pk),
            "series": str(foreign_series.pk),
            "name": "Mismatched",
            "game_type": GameType.NLHE,
            "buy_in_without_rake": "10.00",
            "rake": "1.00",
            "guaranteed_dollars": "100",
            "payout_percent": "15",
            "starting_stack": "10000",
            "starting_stack_bb": "50",
            "timezone": "UTC",
            "late_registration_available": "on",
            "starting_time_0": "01.05.2026",
            "starting_time_1": "20:00",
            "late_reg_at_0": "01.05.2026",
            "late_reg_at_1": "20:30",
            "late_reg_level": "12",
            "blind_interval_minutes": "10",
            "break_minutes": "5",
            "players_per_table": "9",
            "players_at_final_table": "9",
            "min_players": "2",
            "max_players": "1000",
            "re_entry": str(ReEntryOption.objects.get(name="unlimited").pk),
            "bubble": str(BubbleOption.objects.get(name="finalized_when_registration_closes").pk),
            "periodicity": str(Periodicity.objects.get(name="one_off").pk),
            "weekdays": ["0", "1", "2", "3", "4", "5", "6"],
            "early_bird": "",
            "early_bird_type": str(EarlyBirdType.objects.get(name="compensated_at_bubble").pk),
            "featured_final_table": "",
        }
    )
    assert not form.is_valid()
    assert "series" in form.errors


@pytest.mark.django_db
def test_series_widget_tags_options_with_room_id(pokerok):
    from apps.tournaments.forms import TournamentSeriesWidget

    series = _default_series(pokerok)
    widget = TournamentSeriesWidget()
    widget.choices = [("", "---------"), (series.pk, series.name)]
    rendered = widget.render("series", series.pk)
    assert f'data-room-id="{pokerok.pk}"' in rendered


@pytest.mark.django_db
def test_recurrence_copies_series_to_children(pokerok):
    daily = Periodicity.objects.get(name="every_24_hours")
    master = _make_tournament(pokerok, periodicity=daily)
    regenerate_series(master)
    children = Tournament.objects.filter(series_master=master)
    assert children.count() > 0
    assert all(c.series_id == master.series_id for c in children)


@pytest.mark.django_db
def test_series_unique_per_room_slug(pokerok):
    TournamentSeries.objects.create(room=pokerok, name="X", slug="x")
    with pytest.raises(IntegrityError):
        TournamentSeries.objects.create(room=pokerok, name="X Two", slug="x")


@pytest.mark.django_db
def test_series_slug_can_repeat_across_rooms(pokerok):
    other = PokerRoom.objects.exclude(pk=pokerok.pk).first()
    assert other is not None
    a = TournamentSeries.objects.create(room=pokerok, name="Daily", slug="daily")
    b = TournamentSeries.objects.create(room=other, name="Daily", slug="daily")
    assert a.pk != b.pk


@pytest.mark.django_db
def test_pokerok_series_seeded_by_migration(pokerok):
    """Migration 0020 should have populated the 24 known Pokerok series."""
    seeded = TournamentSeries.objects.filter(room=pokerok).exclude(slug="default")
    names = set(seeded.values_list("name", flat=True))
    assert {"WSOP Online", "GGMasters", "Daily Guarantees"}.issubset(names)
    assert seeded.count() == 24


@pytest.mark.django_db
def test_series_column_renders_name_without_image(pokerok):
    from apps.tournaments.columns import _fmt_series

    series = TournamentSeries.objects.filter(room=pokerok, slug="wsop-online").first()
    assert series is not None
    assert _fmt_series(series) == "WSOP Online"


def test_series_column_renders_dash_for_none():
    from apps.tournaments.columns import _fmt_series

    assert _fmt_series(None) == "—"


@pytest.mark.django_db
def test_series_column_appears_in_all_columns():
    from apps.tournaments.columns import ALL_COLUMNS, PUBLIC_COLUMNS

    assert any(c.key == "series" for c in ALL_COLUMNS)
    # Series shown on the public list too (not admin_only).
    assert any(c.key == "series" for c in PUBLIC_COLUMNS)


def test_weekdays_has_changed_accepts_int_initial():
    """Regression: admin's add_view calls `form.changed_data` which routes
    to `MultipleChoiceField.has_changed`, and that one calls len() on the
    initial value. Our field stores the model bitmask as an int — make
    sure has_changed normalizes it instead of raising TypeError."""
    from apps.tournaments.forms import WeekdaysBitmaskField

    field = WeekdaysBitmaskField()
    # Mixed scenarios: int matching the submission, int differing, and
    # the None default should all be handled without raising.
    assert field.has_changed(0b1111111, ["0", "1", "2", "3", "4", "5", "6"]) is False
    assert field.has_changed(0b0000001, ["0", "1"]) is True
    assert field.has_changed(None, ["0"]) is True


@pytest.mark.django_db
def test_admin_form_interprets_starting_time_in_picked_timezone(pokerok):
    """The `timezone` form field — not the request's active TZ — decides
    how the wall-clock starting_time is interpreted. Picking Asia/Almaty
    (+5) at 03:28 must persist as 22:28 UTC of the previous day."""
    from zoneinfo import ZoneInfo

    from apps.tournaments.forms import TournamentAdminForm

    form = TournamentAdminForm(
        data={
            "room": str(pokerok.pk),
            "series": str(_default_series(pokerok).pk),
            "name": "Almaty Event",
            "game_type": GameType.NLHE,
            "buy_in_without_rake": "10.00",
            "rake": "1.00",
            "guaranteed_dollars": "100",
            "payout_percent": "15",
            "starting_stack": "10000",
            "starting_stack_bb": "50",
            "timezone": "Asia/Almaty",
            "late_registration_available": "on",
            "starting_time_0": "18.05.2026",
            "starting_time_1": "03:28",
            "late_reg_at_0": "18.05.2026",
            "late_reg_at_1": "03:28",
            "late_reg_level": "12",
            "blind_interval_minutes": "10",
            "break_minutes": "5",
            "players_per_table": "9",
            "players_at_final_table": "9",
            "min_players": "2",
            "max_players": "1000",
            "re_entry": str(ReEntryOption.objects.get(name="unlimited").pk),
            "bubble": str(BubbleOption.objects.get(name="finalized_when_registration_closes").pk),
            "periodicity": str(Periodicity.objects.get(name="one_off").pk),
            "weekdays": ["0", "1", "2", "3", "4", "5", "6"],
            "early_bird": "",
            "early_bird_type": str(EarlyBirdType.objects.get(name="compensated_at_bubble").pk),
            "featured_final_table": "",
        }
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    expected = datetime(2026, 5, 17, 22, 28, tzinfo=UTC)
    assert saved.starting_time == expected
    assert saved.late_reg_at == expected
    # Cross-check: viewing the stored aware datetime in Almaty restores
    # the original wall-clock value.
    assert saved.starting_time.astimezone(ZoneInfo("Asia/Almaty")).hour == 3


# --- payout default + per-room horizon ------------------------------------


@pytest.mark.django_db
def test_payout_percent_default_is_15(pokerok):
    # Build a Tournament without explicitly setting payout_percent so
    # the model default applies.
    series = _default_series(pokerok)
    starting = datetime(2026, 7, 1, 20, 0, tzinfo=UTC)
    t = Tournament(
        room=pokerok,
        series=series,
        name="Default Payout",
        game_type=GameType.NLHE,
        buy_in_total=Decimal("11.00"),
        buy_in_without_rake=Decimal("10.00"),
        rake=Decimal("1.00"),
        guaranteed_dollars=10000,
        starting_stack=10000,
        starting_stack_bb=50,
        starting_time=starting,
        late_reg_at=starting + timedelta(hours=1),
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
    t.save()
    t.refresh_from_db()
    assert t.payout_percent == 15


@pytest.mark.django_db
def test_pokerroom_horizon_days_default_is_30():
    other = PokerRoom.objects.exclude(slug="pokerok").first()
    assert other is not None
    # Non-Pokerok rooms keep the default (data migration only touches pokerok).
    assert other.horizon_days == 30


@pytest.mark.django_db
def test_pokerok_horizon_days_seeded_to_7_by_migration():
    # Don't use the `pokerok` fixture — it resets horizon to 30. Re-fetch
    # the row directly to observe the migration's value.
    room = PokerRoom.objects.get(slug="pokerok")
    assert room.horizon_days == 7


@pytest.mark.django_db
def test_regenerate_series_respects_room_horizon(pokerok):
    pokerok.horizon_days = 7
    pokerok.save(update_fields=["horizon_days"])
    daily = Periodicity.objects.get(name="every_24_hours")
    master = _make_tournament(pokerok, periodicity=daily)
    regenerate_series(master)
    assert Tournament.objects.filter(series_master=master).count() == 7


@pytest.mark.django_db
def test_extend_series_trims_children_beyond_shrunk_horizon(pokerok):
    """Shrinking room.horizon_days drops children that now fall past it,
    even without re-saving the master. Past children stay (historical)."""
    from django.utils import timezone as djtz

    pokerok.horizon_days = 30
    pokerok.save(update_fields=["horizon_days"])
    daily = Periodicity.objects.get(name="every_24_hours")
    now = djtz.now()
    master = _make_tournament(
        pokerok,
        periodicity=daily,
        starting_time=now + timedelta(hours=1),
        late_reg_at=now + timedelta(hours=2),
    )
    regenerate_series(master)
    # 30 children initially.
    assert Tournament.objects.filter(series_master=master).count() == 30

    # Shrink to 7 days. extend_series_to_horizon should trim everything
    # past now + 7 days.
    pokerok.horizon_days = 7
    pokerok.save(update_fields=["horizon_days"])
    extend_series_to_horizon(master, now=now)
    remaining = Tournament.objects.filter(series_master=master)
    horizon = now + timedelta(days=7)
    assert not remaining.filter(starting_time__gt=horizon).exists()
    # Master starts at now + 1h, so children land at now + 1d+1h ...
    # now + 7d+1h. Day 7's child sits 1h past the horizon and gets
    # trimmed, leaving 6.
    assert remaining.count() == 6


@pytest.mark.django_db
def test_extend_series_respects_room_horizon(pokerok):
    from django.utils import timezone as djtz

    pokerok.horizon_days = 7
    pokerok.save(update_fields=["horizon_days"])
    daily = Periodicity.objects.get(name="every_24_hours")
    # Master in the past so extend_series has to roll forward.
    now = djtz.now()
    master_start = now - timedelta(days=60)
    master = _make_tournament(
        pokerok,
        periodicity=daily,
        starting_time=master_start,
        late_reg_at=master_start + timedelta(hours=1),
    )
    # Wipe out the children regenerate_series produced (all in the past
    # anyway) so we can observe the rolling extend window in isolation.
    Tournament.objects.filter(series_master=master).delete()
    created = extend_series_to_horizon(master, now=now)
    # 7-day horizon at daily cadence → far fewer than the 30-day default
    # would have produced. Extend includes one fast-forward slot before
    # `now`, plus 7 daily ticks within (now, now+7d], so allow some
    # slack but ensure the room-scoped horizon is being honoured.
    assert created <= 10
    assert created > 0


# --- blind structure templates ------------------------------------------


def _make_template(name: str, *rows) -> BlindStructureTemplate:
    """Create a template with the given rows.

    `rows` is a sequence of `(level, sb, bb)` or `(level, sb, bb, ante)`
    tuples. Returned template's `.levels` ordering matches input order.
    """
    template = BlindStructureTemplate.objects.create(name=name)
    for row in rows:
        ante = row[3] if len(row) == 4 else 0
        BlindLevelTemplate.objects.create(
            template=template,
            level=row[0],
            small_blind=row[1],
            big_blind=row[2],
            ante=ante,
        )
    return template


@pytest.mark.django_db
def test_template_apply_to_copies_rows_into_tournament(pokerok):
    tournament = _make_tournament(pokerok)
    template = _make_template("Std", (1, 25, 50), (2, 50, 100), (3, 75, 150, 25))
    template.apply_to(tournament)
    rows = list(tournament.blind_levels.order_by("level").values_list(
        "level", "small_blind", "big_blind", "ante"
    ))
    assert rows == [(1, 25, 50, 0), (2, 50, 100, 0), (3, 75, 150, 25)]


@pytest.mark.django_db
def test_template_apply_to_replaces_existing_rows(pokerok):
    tournament = _make_tournament(pokerok)
    for i in range(1, 6):
        BlindStructure.objects.create(
            tournament=tournament, level=i, small_blind=i, big_blind=i * 2
        )
    template = _make_template("Short", (1, 100, 200), (2, 200, 400))
    template.apply_to(tournament)
    assert tournament.blind_levels.count() == 2
    rows = list(tournament.blind_levels.order_by("level").values_list("big_blind", flat=True))
    assert rows == [200, 400]


@pytest.mark.django_db
def test_template_apply_to_idempotent(pokerok):
    tournament = _make_tournament(pokerok)
    template = _make_template("Std", (1, 25, 50), (2, 50, 100))
    template.apply_to(tournament)
    first = list(tournament.blind_levels.order_by("level").values_list(
        "level", "small_blind", "big_blind", "ante"
    ))
    template.apply_to(tournament)
    second = list(tournament.blind_levels.order_by("level").values_list(
        "level", "small_blind", "big_blind", "ante"
    ))
    assert first == second
    assert len(second) == 2


@pytest.mark.django_db
def test_template_create_from_tournament_snapshots_rows(pokerok):
    tournament = _make_tournament(pokerok)
    BlindStructure.objects.create(tournament=tournament, level=1, small_blind=10, big_blind=20)
    BlindStructure.objects.create(tournament=tournament, level=2, small_blind=20, big_blind=40, ante=5)
    template = BlindStructureTemplate.create_from_tournament(tournament, name="From T")
    rows = list(template.levels.order_by("level").values_list(
        "level", "small_blind", "big_blind", "ante"
    ))
    assert rows == [(1, 10, 20, 0), (2, 20, 40, 5)]


@pytest.mark.django_db
def test_template_create_from_tournament_unique_name(pokerok):
    tournament = _make_tournament(pokerok)
    BlindStructure.objects.create(tournament=tournament, level=1, small_blind=10, big_blind=20)
    BlindStructureTemplate.create_from_tournament(tournament, name="Dup")
    with pytest.raises(IntegrityError):
        BlindStructureTemplate.create_from_tournament(tournament, name="Dup")


@pytest.mark.django_db
def test_template_edits_do_not_affect_previously_applied_tournament(pokerok):
    tournament = _make_tournament(pokerok)
    template = _make_template("Std", (1, 25, 50), (2, 50, 100))
    template.apply_to(tournament)
    # Mutate the template after applying.
    template.levels.all().delete()
    BlindLevelTemplate.objects.create(
        template=template, level=1, small_blind=999, big_blind=9999
    )
    tournament.refresh_from_db()
    rows = list(tournament.blind_levels.order_by("level").values_list(
        "level", "small_blind", "big_blind"
    ))
    assert rows == [(1, 25, 50), (2, 50, 100)]


def _admin_post_payload(pokerok, **overrides) -> dict:
    """Base POST body for TournamentAdminForm submissions in tests.

    The inline formset isn't included here — individual tests append
    the `blind_levels-*` keys themselves so they can vary the row set.
    """
    base = {
        "room": str(pokerok.pk),
        "series": str(_default_series(pokerok).pk),
        "name": "TPL Tournament",
        "game_type": GameType.NLHE,
        "buy_in_without_rake": "10.00",
        "rake": "1.00",
        "guaranteed_dollars": "100",
        "payout_percent": "15",
        "starting_stack": "10000",
        "starting_stack_bb": "50",
        "timezone": "UTC",
        "late_registration_available": "on",
        "starting_time_0": "01.05.2026",
        "starting_time_1": "19:00",
        "late_reg_at_0": "01.05.2026",
        "late_reg_at_1": "20:00",
        "late_reg_level": "12",
        "blind_interval_minutes": "10",
        "break_minutes": "5",
        "players_per_table": "9",
        "players_at_final_table": "9",
        "min_players": "2",
        "max_players": "1000",
        "re_entry": str(ReEntryOption.objects.get(name="unlimited").pk),
        "bubble": str(BubbleOption.objects.get(name="finalized_when_registration_closes").pk),
        "periodicity": str(Periodicity.objects.get(name="one_off").pk),
        "weekdays": ["0", "1", "2", "3", "4", "5", "6"],
        "early_bird": "",
        "early_bird_type": str(EarlyBirdType.objects.get(name="compensated_at_bubble").pk),
        "featured_final_table": "",
    }
    base.update(overrides)
    return base


@pytest.mark.django_db
def test_admin_form_save_as_template_validation_rejects_collision(pokerok):
    from apps.tournaments.forms import TournamentAdminForm

    BlindStructureTemplate.objects.create(name="Z")
    data = _admin_post_payload(
        pokerok,
        save_as_template="on",
        save_as_template_name="Z",
    )
    form = TournamentAdminForm(data=data)
    assert not form.is_valid()
    assert "save_as_template_name" in form.errors


@pytest.mark.django_db
def test_admin_form_save_as_template_allows_blank_name(pokerok):
    from apps.tournaments.forms import TournamentAdminForm

    data = _admin_post_payload(
        pokerok,
        save_as_template="on",
        save_as_template_name="",
    )
    form = TournamentAdminForm(data=data)
    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_recurring_children_inherit_template_when_applied_before_regenerate(pokerok):
    """The recurrence helper copies whatever blind_levels the master has
    at the time of the call. `TournamentAdmin.save_related` orders the
    operations as `apply_template → regenerate_series`, so children must
    pick up the template's rows."""
    daily = Periodicity.objects.get(name="every_24_hours")
    master = _make_tournament(pokerok, periodicity=daily, name="MasterT")

    template = _make_template("DailyT", (1, 25, 50), (2, 50, 100), (3, 75, 150))
    template.apply_to(master)
    regenerate_series(master)

    children = Tournament.objects.filter(series_master=master)
    assert children.exists()
    for child in children:
        rows = list(
            child.blind_levels.order_by("level").values_list("level", "big_blind")
        )
        assert rows == [(1, 50), (2, 100), (3, 150)]


@pytest.mark.django_db
def test_admin_auto_template_name_handles_collisions(pokerok):
    from apps.tournaments.admin import TournamentAdmin

    master = _make_tournament(pokerok, name="Daily Bounty")
    BlindStructureTemplate.objects.create(name="Like Daily Bounty")
    BlindStructureTemplate.objects.create(name="Like Daily Bounty (2)")
    name = TournamentAdmin._auto_template_name(master)
    assert name == "Like Daily Bounty (3)"


@pytest.mark.django_db
def test_template_widget_embeds_data_levels_on_options():
    _make_template("WidgetTpl", (1, 25, 50), (2, 50, 100, 10))
    from apps.tournaments.forms import BlindStructureTemplateWidget

    widget = BlindStructureTemplateWidget()
    widget.choices = [(t.pk, t.name) for t in BlindStructureTemplate.objects.all()]
    rendered = widget.render(
        "apply_template",
        None,
        attrs={"id": "id_apply_template"},
    )
    assert "data-levels" in rendered
    # Both level rows from WidgetTpl should be in the embedded JSON.
    assert "[1, 25, 50, 0]" in rendered
    assert "[2, 50, 100, 10]" in rendered


@pytest.mark.django_db
def test_extract_blind_templates_migration_runs_against_seeded_data(pokerok):
    """Invoke the 0026 migration's `extract` against a freshly-seeded
    fixture. Verifies dedup-by-signature, skip-empty, and the auto-name
    "Like <tournament>" scheme."""
    import importlib

    mig = importlib.import_module(
        "apps.tournaments.migrations.0026_extract_blind_templates"
    )

    # Three masters: A and B share a signature; C has its own; D has no
    # blind_levels at all and must be skipped.
    a = _make_tournament(pokerok, name="ShapeAlpha")
    b = _make_tournament(
        pokerok, name="ShapeBeta",
        starting_time=a.starting_time + timedelta(hours=1),
        late_reg_at=a.late_reg_at + timedelta(hours=1),
    )
    c = _make_tournament(
        pokerok, name="ShapeGamma",
        starting_time=a.starting_time + timedelta(hours=2),
        late_reg_at=a.late_reg_at + timedelta(hours=2),
    )
    _ = _make_tournament(  # no blind_levels - should be skipped
        pokerok, name="ShapeDelta",
        starting_time=a.starting_time + timedelta(hours=3),
        late_reg_at=a.late_reg_at + timedelta(hours=3),
    )
    BlindStructure.objects.create(tournament=a, level=1, small_blind=25, big_blind=50)
    BlindStructure.objects.create(tournament=b, level=1, small_blind=25, big_blind=50)
    BlindStructure.objects.create(tournament=c, level=1, small_blind=100, big_blind=200)

    # Wipe any templates the migration may have already created when the
    # test DB was bootstrapped, so the post-conditions below are
    # observable without ambiguity.
    BlindStructureTemplate.objects.all().delete()

    # `apps` arg in a migration is the historical model registry; using
    # `django.apps.apps` exercises the same code path with live models,
    # which is what's available in tests.
    from django.apps import apps as live_apps

    mig.extract(live_apps, schema_editor=None)

    names = set(BlindStructureTemplate.objects.values_list("name", flat=True))
    # Two unique signatures across A/B/C; "Like ShapeDelta" must NOT
    # appear because that tournament had no blind_levels.
    assert len(names) == 2
    assert "Like ShapeDelta" not in names
    # First master per signature wins → A's name, not B's.
    assert "Like ShapeAlpha" in names
    assert "Like ShapeGamma" in names
