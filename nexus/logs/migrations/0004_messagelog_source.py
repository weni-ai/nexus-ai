# Generated by Django 4.2.10 on 2024-10-17 14:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('logs', '0003_messagelog_groundedness_score_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='messagelog',
            name='source',
            field=models.CharField(max_length=255, null=True),
        ),
    ]
