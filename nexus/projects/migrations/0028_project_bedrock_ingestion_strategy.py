# Generated manually for fast knowledge base ingestion prototype

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0027_alter_project_inline_agent_switch_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="bedrock_ingestion_strategy",
            field=models.CharField(
                choices=[
                    ("job", "Job only"),
                    ("direct", "Direct only"),
                    ("direct_with_fallback", "Direct with fallback"),
                ],
                default="job",
                max_length=32,
            ),
        ),
    ]
