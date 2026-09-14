from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0035_backfill_prompt_injection_filter_existing_false"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="is_live_desk_copilot",
            field=models.BooleanField(
                default=False,
                help_text="When True, this project is a Live Desk sales assistant copilot and cannot change manager version",
            ),
        ),
    ]
