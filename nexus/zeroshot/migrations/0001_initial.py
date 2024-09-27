# Generated by Django 4.2.10 on 2024-09-24 17:15

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ZeroshotLogs',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField(help_text='Text to analyze')),
                ('classification', models.TextField()),
                ('other', models.BooleanField()),
                ('options', models.JSONField()),
                ('nlp_log', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='created at')),
                ('language', models.CharField(blank=True, max_length=64, null=True, verbose_name='Language')),
            ],
            options={
                'verbose_name': 'zeroshot nlp logs',
                'indexes': [models.Index(fields=['nlp_log'], name='common_zeroshot_log_idx')],
            },
        ),
    ]