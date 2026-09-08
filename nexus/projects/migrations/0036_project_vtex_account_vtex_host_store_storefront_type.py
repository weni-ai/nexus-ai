from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0035_backfill_prompt_injection_filter_existing_false"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="storefront_type",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="project",
            name="vtex_account",
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="project",
            name="vtex_host_store",
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
    ]
