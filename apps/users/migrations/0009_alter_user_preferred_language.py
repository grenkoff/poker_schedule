from django.db import migrations, models


def _migrate_ru_users_to_en(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(preferred_language="ru").update(preferred_language="en")


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0008_alter_user_preferred_language'),
    ]

    operations = [
        migrations.RunPython(_migrate_ru_users_to_en, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='user',
            name='preferred_language',
            field=models.CharField(choices=[('en', 'English')], default='en', max_length=10, verbose_name='preferred language'),
        ),
    ]
