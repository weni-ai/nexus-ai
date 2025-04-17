# Generated by Django 4.2.10 on 2025-04-08 14:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0009_project_agents_backend'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='human_support',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='project',
            name='human_support_prompt',
            field=models.TextField(blank=True, null=True),
        ),
    ]
