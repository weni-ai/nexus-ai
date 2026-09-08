from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0033_backfill_projectguardrailsconfig_unblocked"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectguardrailsconfig",
            name="prompt_injection_filter_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
