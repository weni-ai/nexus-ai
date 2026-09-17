from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0039_project_is_live_desk_copilot"),
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
