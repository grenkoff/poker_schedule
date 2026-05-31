"""Reinterpret `Tournament.weekdays` from the UTC frame to the tournament's
own (local) timezone frame.

Until now the recurrence generator filtered occurrences by the UTC weekday of
`starting_time`, and the admin form validated the mask against the UTC weekday
too — so existing masks effectively live in the UTC frame. The rework filters
by the LOCAL weekday (so sub-daily-on-specific-days works correctly), which
means the stored mask must be rotated so the observable schedule is unchanged.

For each recurring master we shift the mask bits by
`delta = local_date(starting_time) - utc_date(starting_time)` (in {-1, 0, +1}).
The all-days mask (127) and the empty mask (0) are rotation-invariant, so the
common case is a no-op. Children are mirrored from their master to avoid a
transient wrong-weekday window before the next regenerate/extend.
"""

from zoneinfo import ZoneInfo

from django.db import migrations


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def to_local_frame(apps, schema_editor):
    Tournament = apps.get_model("tournaments", "Tournament")
    masters = Tournament.objects.filter(
        series_master__isnull=True,
        periodicity__interval_seconds__gt=0,
    ).select_related("periodicity")

    for m in masters:
        mask = m.weekdays or 0
        if mask in (0, 0b1111111):
            continue  # rotation-invariant
        tz = _zone(m.timezone)
        st = m.starting_time  # aware UTC
        delta = (st.astimezone(tz).date() - st.date()).days  # -1, 0, or +1
        if delta == 0:
            continue
        new = 0
        for i in range(7):
            if mask & (1 << i):
                new |= 1 << ((i + delta) % 7)
        if new != mask:
            m.weekdays = new
            m.save(update_fields=["weekdays"])

    # Mirror each (possibly updated) master mask onto its children.
    for m in masters:
        Tournament.objects.filter(series_master=m).update(weekdays=m.weekdays)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0031_collapse_duplicate_templates"),
    ]

    operations = [
        migrations.RunPython(to_local_frame, noop),
    ]
