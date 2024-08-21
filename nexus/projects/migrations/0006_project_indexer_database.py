# Generated by Django 4.2.10 on 2024-08-20 19:20

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0005_projectauth'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='indexer_database',
            field=models.CharField(choices=[('SENTENX', 'Sentenx'), ('BEDROCK', 'Bedrock')], default='SENTENX', max_length=15),
        ),
    ]
