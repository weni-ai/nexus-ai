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
    ]
