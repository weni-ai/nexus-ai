# Generated by Django 4.2.10 on 2024-10-18 14:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0009_auto_20241018_1409'),
    ]

    operations = [
        migrations.AlterField(
            model_name='flow',
            name='flow_uuid',
            field=models.UUIDField(unique=False),
        ),
    ]
