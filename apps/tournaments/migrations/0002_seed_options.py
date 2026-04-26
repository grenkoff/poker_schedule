"""Seed initial values for the three option lookup tables.

The defaults match the spec at the time the form was designed; admins can
add more rows from `/admin/tournaments/{reentryoption,bubbleoption,
earlybirdtype}/`. Idempotent via `update_or_create` so re-running the
migration on a populated DB only refreshes labels.
"""

from django.db import migrations

REENTRY = [
    ("unlimited", "Unlimited re-entries", 10),
    ("none", "No re-entry (freezeout)", 20),
    ("1x", "1 re-entry", 30),
    ("2x", "2 re-entries", 40),
]

BUBBLE = [
    ("finalized_when_registration_closes", "Finalized when registration closes", 10),
]

EARLY_BIRD = [
    (
        "compensated_at_bubble",
        "Buy-in will be compensated if eliminated at the bubble",
        10,
    ),
]


def seed(apps, _schema_editor):
    ReEntryOption = apps.get_model("tournaments", "ReEntryOption")
    BubbleOption = apps.get_model("tournaments", "BubbleOption")
    EarlyBirdType = apps.get_model("tournaments", "EarlyBirdType")

    for model, rows in (
        (ReEntryOption, REENTRY),
        (BubbleOption, BUBBLE),
        (EarlyBirdType, EARLY_BIRD),
    ):
        for name, label, sort_order in rows:
            model.objects.update_or_create(
                name=name,
                defaults={"label": label, "sort_order": sort_order},
            )


def unseed(apps, _schema_editor):
    ReEntryOption = apps.get_model("tournaments", "ReEntryOption")
    BubbleOption = apps.get_model("tournaments", "BubbleOption")
    EarlyBirdType = apps.get_model("tournaments", "EarlyBirdType")
    ReEntryOption.objects.filter(name__in=[r[0] for r in REENTRY]).delete()
    BubbleOption.objects.filter(name__in=[r[0] for r in BUBBLE]).delete()
    EarlyBirdType.objects.filter(name__in=[r[0] for r in EARLY_BIRD]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, reverse_code=unseed),
    ]
