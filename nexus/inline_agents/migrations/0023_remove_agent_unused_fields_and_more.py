from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inline_agents', '0022_add_slug_to_mcp_and_mcps_to_group'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='agent',
            name='capabilities',
        ),
        migrations.RemoveField(
            model_name='agent',
            name='catalog',
        ),
        migrations.RemoveField(
            model_name='agent',
            name='policies',
        ),
        migrations.RemoveField(
            model_name='agent',
            name='tooling',
        ),
        migrations.RemoveField(
            model_name='agent',
            name='variant',
        ),
        migrations.RemoveField(
            model_name="agent",
            name="constants",
        ),
        migrations.AddField(
            model_name='agentgroupmodal',
            name='about',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='agentgroupmodal',
            name='agent_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='agentsystem',
            name='logo',
            field=models.FileField(
                blank=True,
                null=True,
                storage=nexus.storage.AgentSystemLogoStorage(),
                validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['png', 'svg'])],
            ),
        ),
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
