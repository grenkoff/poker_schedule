"""Add Periodicity lookup, seed it, and link Tournament to it.

The `periodicity` FK on Tournament is non-nullable, so the seed step
runs between model creation and the FK addition. Existing Tournament
rows get backfilled to the "one-off" row.

`series_master` is a self-FK pointing at the master Tournament for
auto-generated occurrences in a recurring series.
"""

import django.db.models.deletion
from django.db import migrations, models

PERIODICITY_ROWS = [
    ("one_off", "One-off (specific date and time)", 0, 10),
    ("every_4_hours", "Every 4 hours", 4 * 60 * 60, 20),
    ("every_24_hours", "Every 24 hours", 24 * 60 * 60, 30),
    ("weekly", "Every week", 7 * 24 * 60 * 60, 40),
]


def seed_and_backfill(apps, _schema_editor):
    Periodicity = apps.get_model("tournaments", "Periodicity")
    for name, label, interval_seconds, sort_order in PERIODICITY_ROWS:
        Periodicity.objects.update_or_create(
            name=name,
            defaults={
                "label": label,
                "interval_seconds": interval_seconds,
                "sort_order": sort_order,
            },
        )

    Tournament = apps.get_model("tournaments", "Tournament")
    one_off = Periodicity.objects.get(name="one_off")
    Tournament.objects.filter(periodicity__isnull=True).update(periodicity=one_off)


def unseed(apps, _schema_editor):
    Periodicity = apps.get_model("tournaments", "Periodicity")
    Periodicity.objects.filter(name__in=[r[0] for r in PERIODICITY_ROWS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0002_seed_options"),
    ]

    operations = [
        migrations.CreateModel(
            name="Periodicity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.SlugField(max_length=64, unique=True, verbose_name="name")),
                ("label", models.CharField(max_length=200, verbose_name="label")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="sort order")),
                (
                    "interval_seconds",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Set to 0 for one-off tournaments. Otherwise, seconds between occurrences.",
                        verbose_name="interval (seconds)",
                    ),
                ),
            ],
            options={
                "verbose_name": "periodicity",
                "verbose_name_plural": "periodicities",
                "ordering": ("sort_order", "label"),
                "abstract": False,
            },
        ),
        migrations.AddField(
            model_name="tournament",
            name="series_master",
            field=models.ForeignKey(
                blank=True,
                help_text="Filled in for auto-generated occurrences of a recurring tournament.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="series_children",
                to="tournaments.tournament",
                verbose_name="series master",
            ),
        ),
        migrations.AddField(
            model_name="tournament",
            name="periodicity",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tournaments",
                to="tournaments.periodicity",
                verbose_name="periodicity",
            ),
        ),
        migrations.RunPython(seed_and_backfill, reverse_code=unseed),
        migrations.AlterField(
            model_name="tournament",
            name="periodicity",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tournaments",
                to="tournaments.periodicity",
                verbose_name="periodicity",
            ),
        ),
    ]
