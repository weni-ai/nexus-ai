from django.db import migrations, models


def backfill_agent_constants_from_mcp_options(apps, schema_editor):
    """Copy MCP config option schemas onto agents that lack AgentConstant rows.

    The legacy ``Agent.constants`` JSONField was removed in migration 0023 before
    this table existed, so that data cannot be recovered here. Agents that only
    synced constants through linked MCPs still have schemas in ``MCPConfigOption``.
    Standalone agents without a re-push must be updated from weni-cli YAML.
    """
    Agent = apps.get_model("inline_agents", "Agent")
    AgentConstant = apps.get_model("inline_agents", "AgentConstant")
    MCPConfigOption = apps.get_model("inline_agents", "MCPConfigOption")

    for agent in Agent.objects.iterator():
        if AgentConstant.objects.filter(agents=agent).exists():
            continue

        mcp_ids = list(agent.mcps.values_list("pk", flat=True))
        if not mcp_ids:
            continue

        for option in MCPConfigOption.objects.filter(mcp_id__in=mcp_ids).order_by("order", "name"):
            row, _created = AgentConstant.objects.get_or_create(
                project_id=agent.project_id,
                key=option.name,
                defaults={
                    "label": option.label,
                    "type": option.type,
                    "options": option.options,
                    "default_value": option.default_value,
                    "is_required": option.is_required,
                    "definition": {},
                },
            )
            row.agents.add(agent)


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
                        on_delete=models.CASCADE,
                        related_name="inline_constants",
                        to="projects.project",
                    ),
                ),
            ],
            options={
                "unique_together": {("project", "key")},
            },
        ),
        migrations.RunPython(
            backfill_agent_constants_from_mcp_options,
            migrations.RunPython.noop,
        ),
    ]
