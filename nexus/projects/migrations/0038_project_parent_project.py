from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0036_project_is_live_desk_copilot"),
        ("projects", "0037_alter_project_indexer_database_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="parent_project",
            field=models.ForeignKey(
                blank=True,
                help_text="Main Live Desk project that owns the VTEX account for this copilot",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="live_desk_copilots",
                to="projects.project",
            ),
        ),
    ]
