from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inline_agents", "0034_manageragent_is_live_desk_copilot"),
    ]

    operations = [
        migrations.AddField(
            model_name="inlineagentmessage",
            name="rationale_index",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
