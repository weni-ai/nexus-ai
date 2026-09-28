from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inline_agents", "0032_manageragent_enable_explicit_prompt_cache"),
    ]

    operations = [
        migrations.AddField(
            model_name="inlineagentmessage",
            name="message_kind",
            field=models.CharField(
                blank=True,
                choices=[("rationale", "Rationale"), ("final_response", "Final response")],
                max_length=32,
                null=True,
            ),
        ),
    ]
