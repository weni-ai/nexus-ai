from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('inline_agents', '0024_remove_agent_constants'),
    ]

    operations = [
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
    ]
