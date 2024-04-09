# Generated by Django 4.2.10 on 2024-04-03 19:41

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('intelligences', '0014_llm'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContentBaseInstruction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('instruction', models.TextField()),
                ('content_base', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='instructions', to='intelligences.contentbase')),
            ],
        ),
        migrations.CreateModel(
            name='ContentBaseAgent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, null=True)),
                ('role', models.CharField(max_length=255, null=True)),
                ('personality', models.CharField(max_length=255, null=True)),
                ('goal', models.TextField()),
                ('content_base', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='agent', to='intelligences.contentbase')),
            ],
        ),
    ]