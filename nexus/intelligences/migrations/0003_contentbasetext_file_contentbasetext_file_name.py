# Generated by Django 4.2.8 on 2024-01-22 18:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('intelligences', '0002_contentbasefile_file_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='contentbasetext',
            name='file',
            field=models.URLField(default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='contentbasetext',
            name='file_name',
            field=models.CharField(default='', max_length=255),
            preserve_default=False,
        ),
    ]
