"""Drop scraper-related state.

The scraping pipeline was removed; tournaments are entered manually now.
This migration first deletes any rows that were brought in by a scraper
(identified by `source_kind="scraped"`), then drops the three fields the
scraper layer used to populate.
"""

from django.db import migrations


def delete_scraped_rows(apps, _schema_editor):
    Tournament = apps.get_model("tournaments", "Tournament")
    Tournament.objects.filter(source_kind="scraped").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(delete_scraped_rows, reverse_code=migrations.RunPython.noop),
        migrations.RemoveField(model_name="tournament", name="raw_payload"),
        migrations.RemoveField(model_name="tournament", name="scraped_at"),
        migrations.RemoveField(model_name="tournament", name="source_kind"),
    ]
