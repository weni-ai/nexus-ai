from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0035_backfill_prompt_injection_filter_existing_false"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectguardrailsconfig",
            name="prompt_injection_filter_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
