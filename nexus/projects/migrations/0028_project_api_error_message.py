from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0027_alter_project_inline_agent_switch_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="api_error_message",
            field=models.TextField(blank=True, null=True),
        ),
    ]
