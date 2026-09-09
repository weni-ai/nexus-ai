from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0037_project_is_live_desk_copilot"),
    ]

    operations = [
        migrations.AlterField(
            model_name="project",
            name="indexer_database",
            field=models.CharField(
                choices=[("SENTENX", "Sentenx"), ("BEDROCK", "Bedrock")],
                default="BEDROCK",
                max_length=15,
            ),
        ),
    ]
