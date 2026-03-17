from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inline_agents", "0026_integratedagent_is_active"),
    ]

    operations = [
        migrations.AlterField(
            model_name="manageragent",
            name="max_tokens",
            field=models.PositiveIntegerField(blank=True, default=2048, null=True),
        ),
        migrations.AlterField(
            model_name="manageragent",
            name="collaborator_max_tokens",
            field=models.PositiveIntegerField(blank=True, default=2048, null=True),
        ),
        migrations.AlterField(
            model_name="manageragent",
            name="audio_orchestration_max_tokens",
            field=models.PositiveIntegerField(blank=True, default=2048, null=True),
        ),
        migrations.AlterField(
            model_name="manageragent",
            name="audio_orchestration_collaborator_max_tokens",
            field=models.PositiveIntegerField(blank=True, default=2048, null=True),
        ),
    ]
