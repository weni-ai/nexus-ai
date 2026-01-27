from django.db import migrations, models
import django.core.validators
import nexus.storage

class Migration(migrations.Migration):

    dependencies = [
        ('inline_agents', '0025_agentgroupmodal_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agentsystem',
            name='logo',
            field=models.FileField(
                blank=True,
                null=True,
                storage=nexus.storage.AgentSystemLogoStorage(),
                upload_to='agent_systems/logos/',
                validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['png', 'svg'])],
            ),
        ),
    ]
