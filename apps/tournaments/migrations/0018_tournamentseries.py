import django.db.models.deletion
from django.db import migrations, models


def backfill_default_series(apps, schema_editor):
    """Create one 'Default' TournamentSeries per existing room and
    assign every existing Tournament to its room's default."""
    PokerRoom = apps.get_model("rooms", "PokerRoom")
    Tournament = apps.get_model("tournaments", "Tournament")
    TournamentSeries = apps.get_model("tournaments", "TournamentSeries")

    for room in PokerRoom.objects.all():
        default, _ = TournamentSeries.objects.get_or_create(
            room=room,
            slug="default",
            defaults={"name": "Default", "sort_order": 0},
        )
        Tournament.objects.filter(room=room, series__isnull=True).update(series=default)


def noop(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("rooms", "0001_initial"),
        ("tournaments", "0017_tournament_weekdays"),
    ]

    operations = [
        migrations.CreateModel(
            name="TournamentSeries",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120, verbose_name="name")),
                ("slug", models.SlugField(max_length=120, verbose_name="slug")),
                (
                    "sort_order",
                    models.PositiveIntegerField(default=0, verbose_name="sort order"),
                ),
                (
                    "room",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tournament_series",
                        to="rooms.pokerroom",
                        verbose_name="room",
                    ),
                ),
            ],
            options={
                "verbose_name": "tournament series",
                "verbose_name_plural": "tournament series",
                "ordering": ("room__name", "sort_order", "name"),
            },
        ),
        migrations.AddConstraint(
            model_name="tournamentseries",
            constraint=models.UniqueConstraint(
                fields=("room", "slug"),
                name="tournamentseries_unique_room_slug",
            ),
        ),
        # Step 1: add `series` to Tournament as nullable so existing rows
        # don't violate the constraint while we backfill.
        migrations.AddField(
            model_name="tournament",
            name="series",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tournaments",
                to="tournaments.tournamentseries",
                verbose_name="tournament series",
            ),
        ),
        # Step 2: backfill every existing row to a per-room "Default" series.
        migrations.RunPython(backfill_default_series, noop),
        # Step 3: tighten the constraint — series is now required.
        migrations.AlterField(
            model_name="tournament",
            name="series",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tournaments",
                to="tournaments.tournamentseries",
                verbose_name="tournament series",
            ),
        ),
    ]
