# Generated by Django 4.2.10 on 2024-09-04 14:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0003_templateaction_alter_flow_action_type_and_more'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='flow',
            name='unique_action_type_except_custom',
        ),
        migrations.AddConstraint(
            model_name='flow',
            constraint=models.UniqueConstraint(condition=models.Q(('action_type', 'custom'), _negated=True), fields=('action_type', 'action_type'), name='unique_action_type_except_custom_per_content_base'),
        ),
    ]