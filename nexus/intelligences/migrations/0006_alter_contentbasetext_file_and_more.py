# Generated by Django 4.2.8 on 2024-01-25 20:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('intelligences', '0005_merge_20240124_1745'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contentbasetext',
            name='file',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='contentbasetext',
            name='file_name',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
