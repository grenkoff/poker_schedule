from django.db import migrations


def set_pokerok_horizon(apps, schema_editor):
    PokerRoom = apps.get_model("rooms", "PokerRoom")
    PokerRoom.objects.filter(slug="pokerok").update(horizon_days=7)


def reset_pokerok_horizon(apps, schema_editor):
    PokerRoom = apps.get_model("rooms", "PokerRoom")
    PokerRoom.objects.filter(slug="pokerok").update(horizon_days=30)


class Migration(migrations.Migration):

    dependencies = [
        ("rooms", "0005_pokerroom_horizon_days"),
    ]

    operations = [
        migrations.RunPython(set_pokerok_horizon, reset_pokerok_horizon),
    ]
