"""Backfill `role` for users created before the field existed.

`is_superuser=True` becomes SUPERADMIN, `is_staff=True` (without superuser)
becomes ADMIN, everyone else stays USER (the default). This keeps the
existing `admin` superuser working — they end up SUPERADMIN.
"""

from django.db import migrations


def backfill_role(apps, _schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(is_superuser=True).update(role="superadmin")
    User.objects.filter(is_staff=True, is_superuser=False).update(role="admin")
    # USER is the default; rows already have role="user".


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0002_alter_user_managers_user_role"),
    ]

    operations = [
        migrations.RunPython(backfill_role, reverse_code=migrations.RunPython.noop),
    ]
