# Generated by Django 4.2.10 on 2025-01-08 17:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0002_agent_description_agentskills'),
    ]

    operations = [
        migrations.AddField(
            model_name='activeagent',
            name='metadata',
            field=models.JSONField(default=dict),
        ),
    ]
