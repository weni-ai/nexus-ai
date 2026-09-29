from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inline_agents", "0032_manageragent_enable_explicit_prompt_cache"),
    ]

    operations = [
        migrations.AddField(
            model_name="manageragent",
            name="is_live_desk_copilot",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "If True, new Live Desk copilot projects are created with this manager. "
                    "Keep default unchecked so normal projects do not use it."
                ),
            ),
        ),
    ]
