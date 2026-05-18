"""Reconcile existing child rows against `room.horizon_days`.

`extend_series_to_horizon` now trims future children that fall outside
the room's horizon, but rows created before that change (e.g. Pokerok
masters generated at the old 30-day default) are still in the DB. Walk
every master once and delete future-only children beyond its horizon.
"""

from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def trim_future_children(apps, schema_editor):
    Tournament = apps.get_model("tournaments", "Tournament")
    now = timezone.now()
    masters = Tournament.objects.filter(
        series_master__isnull=True,
        periodicity__interval_seconds__gt=0,
    ).select_related("room")
    for master in masters:
        horizon_days = getattr(master.room, "horizon_days", 30) or 30
        horizon = now + timedelta(days=horizon_days)
        Tournament.objects.filter(
            series_master=master,
            starting_time__gt=horizon,
        ).delete()


def noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("tournaments", "0023_alter_tournament_payout_percent"),
        ("rooms", "0006_pokerok_horizon_7"),
    ]

    operations = [
        migrations.RunPython(trim_future_children, noop),
    ]
