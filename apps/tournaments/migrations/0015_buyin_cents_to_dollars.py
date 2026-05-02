from decimal import Decimal

from django.db import migrations, models


def cents_to_dollars(apps, schema_editor):
    Tournament = apps.get_model("tournaments", "Tournament")
    for t in Tournament.objects.all():
        t.buy_in_total = Decimal(t.buy_in_total_cents) / Decimal(100)
        t.buy_in_without_rake = Decimal(t.buy_in_without_rake_cents) / Decimal(100)
        t.rake = Decimal(t.rake_cents) / Decimal(100)
        t.save(update_fields=["buy_in_total", "buy_in_without_rake", "rake"])


def dollars_to_cents(apps, schema_editor):
    Tournament = apps.get_model("tournaments", "Tournament")
    for t in Tournament.objects.all():
        t.buy_in_total_cents = int((t.buy_in_total * 100).to_integral_value())
        t.buy_in_without_rake_cents = int((t.buy_in_without_rake * 100).to_integral_value())
        t.rake_cents = int((t.rake * 100).to_integral_value())
        t.save(update_fields=["buy_in_total_cents", "buy_in_without_rake_cents", "rake_cents"])


class Migration(migrations.Migration):

    dependencies = [
        ("tournaments", "0014_alter_tournament_starting_stack_and_more"),
    ]

    operations = [
        # 1. Add new decimal fields (nullable to allow data migration)
        migrations.AddField(
            model_name="tournament",
            name="buy_in_total",
            field=models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name="buy-in (with rake), $"),
        ),
        migrations.AddField(
            model_name="tournament",
            name="buy_in_without_rake",
            field=models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name="buy-in (without rake), $"),
        ),
        migrations.AddField(
            model_name="tournament",
            name="rake",
            field=models.DecimalField(decimal_places=2, max_digits=10, null=True, verbose_name="rake, $"),
        ),
        # 2. Populate new fields from old
        migrations.RunPython(cents_to_dollars, reverse_code=dollars_to_cents),
        # 3. Make new fields required
        migrations.AlterField(
            model_name="tournament",
            name="buy_in_total",
            field=models.DecimalField(decimal_places=2, max_digits=10, verbose_name="buy-in (with rake), $"),
        ),
        migrations.AlterField(
            model_name="tournament",
            name="buy_in_without_rake",
            field=models.DecimalField(decimal_places=2, max_digits=10, verbose_name="buy-in (without rake), $"),
        ),
        migrations.AlterField(
            model_name="tournament",
            name="rake",
            field=models.DecimalField(decimal_places=2, max_digits=10, verbose_name="rake, $"),
        ),
        # 4. Remove old integer fields and their index
        migrations.RemoveIndex(
            model_name="tournament",
            name="tournaments_buy_in__dc533b_idx",
        ),
        migrations.RemoveField(model_name="tournament", name="buy_in_total_cents"),
        migrations.RemoveField(model_name="tournament", name="buy_in_without_rake_cents"),
        migrations.RemoveField(model_name="tournament", name="rake_cents"),
        # 5. Add new index on buy_in_total
        migrations.AddIndex(
            model_name="tournament",
            index=models.Index(fields=["buy_in_total"], name="tournaments_buy_in_total_idx"),
        ),
    ]
