from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inline_agents", "0033_inlineagentmessage_message_kind"),
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
        migrations.AddConstraint(
            model_name="manageragent",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_live_desk_copilot", True)),
                fields=("is_live_desk_copilot",),
                name="unique_live_desk_copilot_manager",
                violation_error_message=(
                    "Another manager is already marked as Live Desk copilot. Uncheck it before marking this one."
                ),
            ),
        ),
    ]
