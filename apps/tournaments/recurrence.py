"""Materialize future occurrences of a recurring Tournament.

A Tournament whose `periodicity.interval_seconds > 0` and that is not
itself a child of a series (i.e. `series_master_id is None`) is a
*master*. We generate sibling Tournament rows for every shifted start
time that falls within `master.room.horizon_days` from the relevant
base time, so different rooms can curate different forward windows.

`regenerate_series` wipes and re-creates all children from
`master.starting_time + delta` up to `master.starting_time + horizon`;
it is invoked when the master is saved.

`extend_series_to_horizon` is append-only: it adds children up to
`now() + horizon` without touching existing rows. It is invoked lazily
from the admin changelist so the visible horizon stays rolling even
when the master is not re-saved.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

# Fallback used only when a master has no room (shouldn't happen in
# normal data) — production rows always pull from `room.horizon_days`.
HORIZON_DAYS = 30

# Anything at or above this interval is treated as "≥ daily": we step one
# day at a time and let the weekday mask decide which days produce an
# occurrence (so e.g. weekly with Mon+Thu yields BOTH Mondays and
# Thursdays, not just one weekday).
_DAILY_SECONDS = 86400


def _horizon_for(master) -> int:
    room = getattr(master, "room", None)
    return getattr(room, "horizon_days", None) or HORIZON_DAYS


def _tz_for(master) -> ZoneInfo:
    """The tournament's own timezone (the frame the weekday mask lives in)."""
    try:
        return ZoneInfo(master.timezone or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def _step_for(interval_seconds: int) -> timedelta:
    """Iteration step. For ≥ daily intervals we step one day so each
    selected local weekday gets its own occurrence; for sub-daily we step
    by the true interval (the start time is a within-day phase anchor)."""
    if interval_seconds >= _DAILY_SECONDS:
        return timedelta(days=1)
    return timedelta(seconds=interval_seconds)


def _allowed_weekdays(mask: int) -> set[int]:
    """Unpack the 7-bit weekday mask. Empty mask is treated as "all days"
    so legacy or corrupted data doesn't stall the generator."""
    days = {i for i in range(7) if mask & (1 << i)}
    return days or set(range(7))


def _build_child(master, next_start: datetime, late_reg_offset: timedelta):
    from .models import Tournament

    return Tournament(
        room=master.room,
        series=master.series,
        name=master.name,
        game_type=master.game_type,
        buy_in_total=master.buy_in_total,
        buy_in_without_rake=master.buy_in_without_rake,
        bounty_buyin=master.bounty_buyin,
        rake=master.rake,
        guaranteed_dollars=master.guaranteed_dollars,
        payout_percent=master.payout_percent,
        starting_stack=master.starting_stack,
        starting_stack_bb=master.starting_stack_bb,
        starting_time=next_start,
        late_registration_available=master.late_registration_available,
        late_reg_at=next_start + late_reg_offset,
        late_reg_level=master.late_reg_level,
        blind_interval_minutes=master.blind_interval_minutes,
        break_minutes=master.break_minutes,
        players_per_table=master.players_per_table,
        players_at_final_table=master.players_at_final_table,
        min_players=master.min_players,
        max_players=master.max_players,
        re_entry=master.re_entry,
        bubble=master.bubble,
        periodicity=master.periodicity,
        weekdays=master.weekdays,
        series_master=master,
        early_bird=master.early_bird,
        early_bird_type=master.early_bird_type,
        is_bounty=master.is_bounty,
        bounty_type=master.bounty_type,
        min_bounty=master.min_bounty,
        featured_final_table=master.featured_final_table,
        verified_by_admin=master.verified_by_admin,
    )


def _copy_blind_levels(child, blind_levels) -> None:
    from .models import BlindStructure

    for level in blind_levels:
        BlindStructure.objects.create(
            tournament=child,
            level=level.level,
            small_blind=level.small_blind,
            big_blind=level.big_blind,
            ante=level.ante,
        )


@transaction.atomic
def regenerate_series(master) -> None:
    from .models import Tournament

    if master.series_master_id is not None:
        return

    interval = master.periodicity.interval_seconds
    Tournament.objects.filter(series_master=master).delete()

    if not interval:
        return

    step = _step_for(interval)
    tz = _tz_for(master)
    horizon = master.starting_time + timedelta(days=_horizon_for(master))
    late_reg_offset = master.late_reg_at - master.starting_time
    blind_levels = list(master.blind_levels.all())
    allowed = _allowed_weekdays(master.weekdays)

    next_start = master.starting_time + step
    while next_start <= horizon:
        if next_start.astimezone(tz).weekday() in allowed:
            child = _build_child(master, next_start, late_reg_offset)
            child.save()
            _copy_blind_levels(child, blind_levels)
        next_start += step


@transaction.atomic
def extend_series_to_horizon(master, *, now: datetime | None = None) -> int:
    """Append children up to `now + HORIZON_DAYS` without removing existing ones.

    Returns the number of children created. Safe to call repeatedly
    (idempotent once the horizon is reached).
    """
    from .models import Tournament

    if master.series_master_id is not None:
        return 0

    interval = master.periodicity.interval_seconds
    if not interval:
        return 0

    now = now or timezone.now()
    step = _step_for(interval)
    tz = _tz_for(master)
    horizon = now + timedelta(days=_horizon_for(master))

    # If the room's horizon was shrunk (e.g. 30 → 7), drop any FUTURE
    # children that now fall past it. Past children stay as historical
    # data. Reconciles "the DB matches the current horizon" without
    # waiting for the master to be re-saved.
    Tournament.objects.filter(
        series_master=master,
        starting_time__gt=horizon,
    ).delete()

    last_child_start = Tournament.objects.filter(series_master=master).aggregate(
        last=Max("starting_time")
    )["last"]
    base = last_child_start or master.starting_time
    next_start = base + step

    if next_start > horizon:
        return 0

    # Fast-forward when the base is far in the past so we don't create
    # thousands of guaranteed-closed occurrences. Land on the first
    # occurrence at or after `now - step` (one slot of slack so we
    # don't skip an in-progress tournament).
    if next_start < now - step:
        gap = now - step - next_start
        skip = gap.total_seconds() // step.total_seconds()
        next_start = next_start + step * int(skip)

    late_reg_offset = master.late_reg_at - master.starting_time
    blind_levels = list(master.blind_levels.all())
    allowed = _allowed_weekdays(master.weekdays)

    created = 0
    while next_start <= horizon:
        if next_start.astimezone(tz).weekday() in allowed:
            child = _build_child(master, next_start, late_reg_offset)
            child.save()
            _copy_blind_levels(child, blind_levels)
            created += 1
        next_start += step
    return created
