# Generated by Django 4.2.10 on 2024-09-24 14:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0005_remove_flow_unique_action_type_except_custom_per_content_base_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='flow',
            name='action_type',
            field=models.CharField(choices=[('custom', 'Custom'), ('whatsapp_cart', 'WhatsApp Cart'), ('localization', 'Localization'), ('attachment', 'Attachment'), ('safe_guard', 'Safe Guard'), ('prompt_guard', 'Prompt Guard')], default='custom', max_length=50),
        ),
        migrations.AlterField(
            model_name='flow',
            name='group',
            field=models.CharField(choices=[('support', 'Support'), ('interactions', 'Interactions'), ('shopping', 'Shopping'), ('custom', 'Custom'), ('security', 'Security')], default='custom', max_length=255),
        ),
    ]
