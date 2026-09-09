from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0036_project_vtex_account_vtex_host_store_storefront_type"),
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
