# Generated by Django 4.2.10 on 2024-08-20 13:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='flow',
            name='action_type',
            field=models.CharField(choices=[('custom', 'Custom'), ('whatsapp_cart', 'WhatsApp Cart'), ('exchanges', 'Exchanges'), ('offenses', 'Offenses'), ('greetings', 'Greetings')], default='custom', max_length=50),
        ),
        migrations.AddConstraint(
            model_name='flow',
            constraint=models.UniqueConstraint(condition=models.Q(('action_type', 'custom'), _negated=True), fields=('action_type',), name='unique_action_type_except_custom'),
        ),
    ]
