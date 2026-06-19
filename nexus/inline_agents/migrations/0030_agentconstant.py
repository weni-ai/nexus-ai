from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inline_agents", "0029_modelprovider_projectmodelprovider"),
        ("projects", "0027_alter_project_inline_agent_switch_default"),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentConstant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=255)),
                ("label", models.CharField(max_length=255)),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("TEXT", "Text"),
                            ("NUMBER", "Number"),
                            ("CHECKBOX", "Checkbox"),
                            ("SELECT", "Select"),
                            ("RADIO", "Radio"),
                            ("SWITCH", "Switch"),
                        ],
                        default="TEXT",
                        max_length=20,
                    ),
                ),
                ("options", models.JSONField(blank=True, default=list)),
                ("default_value", models.JSONField(blank=True, default=None, null=True)),
                ("is_required", models.BooleanField(default=False)),
                ("definition", models.JSONField(blank=True, default=dict)),
                ("agents", models.ManyToManyField(to="inline_agents.agent")),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="inline_constants",
                        to="projects.project",
                    ),
                ),
            ],
            options={
                "unique_together": {("project", "key")},
            },
        ),
    ]
