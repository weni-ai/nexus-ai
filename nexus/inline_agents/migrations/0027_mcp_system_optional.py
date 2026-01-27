from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inline_agents", "0026_alter_agentsystem_logo"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mcp",
            name="system",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="mcps",
                to="inline_agents.agentsystem",
            ),
        ),
    ]
