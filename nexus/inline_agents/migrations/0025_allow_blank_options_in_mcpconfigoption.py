# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inline_agents", "0024_migrate_trade_policy_unique_seller_to_config_options"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mcpconfigoption",
            name="options",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="For SELECT/RADIO type: [{'name': 'Display', 'value': 'internal'}]",
            ),
        ),
    ]

