from django.db import migrations


SEED_ROWS = [
    # (slug, label, sort_order)
    ("possible_at_final_table", "Possible when players reach final table", 10),
]


def seed(apps, schema_editor):
    DealMakingOption = apps.get_model("tournaments", "DealMakingOption")
    for name, label, sort_order in SEED_ROWS:
        DealMakingOption.objects.update_or_create(
            name=name,
            defaults={"label": label, "sort_order": sort_order},
        )


def unseed(apps, schema_editor):
    DealMakingOption = apps.get_model("tournaments", "DealMakingOption")
    DealMakingOption.objects.filter(name__in=[r[0] for r in SEED_ROWS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tournaments", "0021_dealmaking_and_relax_player_minimums"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
