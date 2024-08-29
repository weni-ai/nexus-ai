# Generated by Django 4.2.10 on 2024-08-29 12:54

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0002_flow_action_type_alter_flow_prompt_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='TemplateAction',
            fields=[
                ('uuid', models.UUIDField(primary_key=True, serialize=False)),
                ('action_type', models.CharField(max_length=255)),
                ('name', models.CharField(max_length=255)),
                ('prompt', models.TextField(blank=True, null=True)),
                ('group', models.CharField(blank=True, max_length=255, null=True)),
            ],
        ),
        migrations.AlterField(
            model_name='flow',
            name='action_type',
            field=models.CharField(choices=[('custom', 'Custom'), ('whatsapp_cart', 'WhatsApp Cart'), ('localization', 'Localization'), ('attachment', 'Attachment')], default='custom', max_length=50),
        ),
        migrations.AddField(
            model_name='flow',
            name='action_template',
            field=models.OneToOneField(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='flows', to='actions.templateaction'),
        ),
    ]
