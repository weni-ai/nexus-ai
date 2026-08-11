from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0034_project_is_live_desk_copilot"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectguardrailsconfig",
            name="prompt_injection_filter_enabled",
            field=models.BooleanField(default=False),
        ),
    ]
