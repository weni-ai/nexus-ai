# Generated by Django 4.2.6 on 2023-11-08 19:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('intelligences', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='intelligence',
            name='description',
            field=models.TextField(blank=True, null=True),
        ),
    ]
