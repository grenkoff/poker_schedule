"""Materialize future occurrences of a recurring Tournament.

A Tournament whose `periodicity.interval_seconds > 0` and that is not
itself a child of a series (i.e. `series_master_id is None`) is a
*master*. We generate sibling Tournament rows for every shifted start
time that falls within `HORIZON_DAYS` from the master's `starting_time`.

Children are full copies of the master with `series_master` set, the
time-related fields shifted, and `BlindStructure` rows duplicated.
Re-saving the master regenerates the children — manual edits to a child
will be lost on the next master save.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction

HORIZON_DAYS = 30


@transaction.atomic
def regenerate_series(master) -> None:
    from .models import BlindStructure, Tournament

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

    next_start = master.starting_time + delta
    while next_start <= horizon:
        child = Tournament(
            room=master.room,
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
            series_master=master,
            early_bird=master.early_bird,
            early_bird_type=master.early_bird_type,
            featured_final_table=master.featured_final_table,
            verified_by_admin=master.verified_by_admin,
        )
        child.save()
        for level in blind_levels:
            BlindStructure.objects.create(
                tournament=child,
                level=level.level,
                small_blind=level.small_blind,
                big_blind=level.big_blind,
                ante=level.ante,
            )
        next_start += delta
