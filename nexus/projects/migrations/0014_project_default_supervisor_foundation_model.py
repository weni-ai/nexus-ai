# Generated by Django 4.2.10 on 2025-06-10 20:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0013_project_use_components'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='default_supervisor_foundation_model',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
