from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0040_project_parent_project"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="timezone",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
