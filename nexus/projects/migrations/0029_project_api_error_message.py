from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0028_project_bedrock_ingestion_strategy"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="api_error_message",
            field=models.TextField(blank=True, null=True),
        ),
    ]
