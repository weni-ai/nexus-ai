# Generated by Django 4.2.10 on 2025-03-20 20:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0010_contactfield'),
    ]

    operations = [
        migrations.AddField(
            model_name='team',
            name='human_support',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='team',
            name='human_support_prompt',
            field=models.TextField(blank=True, null=True),
        ),
    ]
