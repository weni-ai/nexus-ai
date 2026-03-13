from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inline_agents", "0025_alter_agentsystem_logo"),
    ]

    operations = [
        migrations.AddField(
            model_name="integratedagent",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
