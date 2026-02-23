from django.db import migrations, models
import django.core.validators
import nexus.inline_agents.models
import nexus.storage


class Migration(migrations.Migration):

    dependencies = [
        ('inline_agents', '0024_manageragent_append_manager_extra_args_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='agentsystem',
            name='logo',
            field=models.FileField(blank=True, null=True, storage=nexus.storage.AgentSystemLogoStorage(), upload_to=nexus.inline_agents.models.agent_system_logo_upload_to, validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['png', 'svg'])]),
        ),
    ]
