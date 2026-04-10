from django.db import migrations, models


def copy_legacy_to_en(apps, schema_editor):
    """Move former single-locale content into *_en before legacy columns are dropped."""
    MCP = apps.get_model("inline_agents", "MCP")
    AgentGroupModal = apps.get_model("inline_agents", "AgentGroupModal")

    for mcp in MCP.objects.iterator():
        legacy = (getattr(mcp, "description", None) or "").strip()
        if legacy and not (mcp.description_en or "").strip():
            mcp.description_en = mcp.description
            mcp.save(update_fields=["description_en"])

    for modal in AgentGroupModal.objects.iterator():
        update_fields = []
        legacy_about = (getattr(modal, "about", None) or "").strip()
        if legacy_about and not (modal.about_en or "").strip():
            modal.about_en = modal.about
            update_fields.append("about_en")
        legacy_ce = getattr(modal, "conversation_example", None)
        if legacy_ce and not modal.conversation_example_en:
            modal.conversation_example_en = list(legacy_ce)
            update_fields.append("conversation_example_en")
        if update_fields:
            modal.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("inline_agents", "0027_manageragent_max_tokens_optional"),
    ]

    operations = [
        migrations.AddField(
            model_name="mcp",
            name="description_en",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="mcp",
            name="description_es",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="mcp",
            name="description_pt",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="agentgroupmodal",
            name="about_en",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="agentgroupmodal",
            name="about_es",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="agentgroupmodal",
            name="about_pt",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="agentgroupmodal",
            name="conversation_example_en",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="agentgroupmodal",
            name="conversation_example_es",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="agentgroupmodal",
            name="conversation_example_pt",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(copy_legacy_to_en, migrations.RunPython.noop),
        migrations.RemoveField(model_name="mcp", name="description"),
        migrations.RemoveField(model_name="agentgroupmodal", name="about"),
        migrations.RemoveField(model_name="agentgroupmodal", name="conversation_example"),
    ]
