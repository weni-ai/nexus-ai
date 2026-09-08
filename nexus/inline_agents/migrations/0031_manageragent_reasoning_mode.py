from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inline_agents", "0030_agentconstant"),
    ]

    operations = [
        migrations.AddField(
            model_name="manageragent",
            name="reasoning_mode",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
