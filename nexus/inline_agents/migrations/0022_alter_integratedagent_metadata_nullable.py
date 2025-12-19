# Generated manually

from django.db import migrations, models


def populate_metadata_defaults(apps, schema_editor):
    """Populate NULL metadata fields with empty dict"""
    IntegratedAgent = apps.get_model('inline_agents', 'IntegratedAgent')
    # Update all records with NULL metadata to empty dict
    for integrated_agent in IntegratedAgent.objects.filter(metadata__isnull=True):
        integrated_agent.metadata = {}
        integrated_agent.save(update_fields=['metadata'])


def reverse_populate_metadata_defaults(apps, schema_editor):
    """Reverse migration - no action needed"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inline_agents', '0021_add_mcp_models_and_metadata'),
    ]

    operations = [
        # First, populate existing NULL values with empty dict
        migrations.RunPython(
            populate_metadata_defaults,
            reverse_populate_metadata_defaults,
        ),
        # Then, alter the field to allow null=True
        migrations.AlterField(
            model_name='integratedagent',
            name='metadata',
            field=models.JSONField(blank=True, default=dict, null=True),
        ),
    ]

