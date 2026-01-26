from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inline_agents', '0023_remove_agent_unused_fields'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='agent',
            name='constants',
        ),
    ]
