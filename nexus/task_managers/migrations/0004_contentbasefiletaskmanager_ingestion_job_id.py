# Generated by Django 4.2.10 on 2024-08-23 22:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('task_managers', '0003_contentbaselinktaskmanager'),
    ]

    operations = [
        migrations.AddField(
            model_name='contentbasefiletaskmanager',
            name='ingestion_job_id',
            field=models.CharField(null=True),
        ),
    ]
