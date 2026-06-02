"""Seed initial bounty types for the BountyOption lookup table.

Mirrors 0002_seed_options.py: idempotent via update_or_create so re-running
on a populated DB only refreshes labels. Admins can add more rows from
/admin/tournaments/bountyoption/.
"""

from django.db import migrations

BOUNTY = [
    ("progressive", "Progressive Bounty", 10),
    ("mystery", "Mystery Bounty", 20),
    ("standard_ko", "Knockout (Bounty)", 30),
]


def seed(apps, _schema_editor):
    BountyOption = apps.get_model("tournaments", "BountyOption")
    for name, label, sort_order in BOUNTY:
        BountyOption.objects.update_or_create(
            name=name,
            defaults={"label": label, "sort_order": sort_order},
        )


def unseed(apps, _schema_editor):
    BountyOption = apps.get_model("tournaments", "BountyOption")
    BountyOption.objects.filter(name__in=[b[0] for b in BOUNTY]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0033_bountyoption_tournament_bounty_buyin_and_more"),
    ]

    operations = [
        migrations.RunPython(seed, reverse_code=unseed),
    ]
