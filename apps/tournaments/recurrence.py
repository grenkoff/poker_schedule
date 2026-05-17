"""Materialize future occurrences of a recurring Tournament.

A Tournament whose `periodicity.interval_seconds > 0` and that is not
itself a child of a series (i.e. `series_master_id is None`) is a
*master*. We generate sibling Tournament rows for every shifted start
time that falls within `HORIZON_DAYS` from the relevant base time.

`regenerate_series` wipes and re-creates all children from
`master.starting_time + delta` up to `master.starting_time + 30 days`;
it is invoked when the master is saved.

`extend_series_to_horizon` is append-only: it adds children up to
`now() + 30 days` without touching existing rows. It is invoked lazily
from the admin changelist so the visible horizon stays rolling even
when the master is not re-saved.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

HORIZON_DAYS = 30


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

    delta = timedelta(seconds=interval)
    horizon = master.starting_time + timedelta(days=HORIZON_DAYS)
    late_reg_offset = master.late_reg_at - master.starting_time
    blind_levels = list(master.blind_levels.all())
    allowed = _allowed_weekdays(master.weekdays)

    next_start = master.starting_time + delta
    while next_start <= horizon:
        if next_start.weekday() in allowed:
            child = _build_child(master, next_start, late_reg_offset)
            child.save()
            _copy_blind_levels(child, blind_levels)
        next_start += delta


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
    delta = timedelta(seconds=interval)
    horizon = now + timedelta(days=HORIZON_DAYS)

    last_child_start = Tournament.objects.filter(series_master=master).aggregate(
        last=Max("starting_time")
    )["last"]
    base = last_child_start or master.starting_time
    next_start = base + delta

    if next_start > horizon:
        return 0

    # Fast-forward when the base is far in the past so we don't create
    # thousands of guaranteed-closed occurrences. Land on the first
    # occurrence at or after `now - delta` (one slot of slack so we
    # don't skip an in-progress tournament).
    if next_start < now - delta:
        gap = now - delta - next_start
        skip = gap.total_seconds() // delta.total_seconds()
        next_start = next_start + delta * int(skip)

    late_reg_offset = master.late_reg_at - master.starting_time
    blind_levels = list(master.blind_levels.all())
    allowed = _allowed_weekdays(master.weekdays)

    created = 0
    while next_start <= horizon:
        if next_start.weekday() in allowed:
            child = _build_child(master, next_start, late_reg_offset)
            child.save()
            _copy_blind_levels(child, blind_levels)
            created += 1
        next_start += delta
    return created
