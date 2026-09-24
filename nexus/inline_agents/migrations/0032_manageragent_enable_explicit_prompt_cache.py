from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inline_agents", "0031_manageragent_reasoning_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="manageragent",
            name="enable_explicit_prompt_cache",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "If True and model_vendor is aws_mantle, send explicit prompt cache "
                    "(prompt_cache_key / breakpoints) for this manager and its collaborators. "
                    "Leave False unless the selected Mantle model supports explicit cache."
                ),
            ),
        ),
    ]
