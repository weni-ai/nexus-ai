from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0036_project_vtex_account_vtex_host_store_storefront_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="is_live_desk_copilot",
            field=models.BooleanField(
                default=False,
                help_text="When True, this project is a Live Desk sales assistant copilot and cannot change manager version",
            ),
        ),
    ]
