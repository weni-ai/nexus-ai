from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inline_agents', '0027_mcp_system_optional'),
    ]

    operations = [
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
    ]
