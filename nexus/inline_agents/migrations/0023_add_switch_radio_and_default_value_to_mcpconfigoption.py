# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inline_agents', '0022_alter_integratedagent_metadata_nullable'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mcpconfigoption',
            name='type',
            field=models.CharField(
                choices=[
                    ('CHECKBOX', 'Checkbox'),
                    ('SELECT', 'Select'),
                    ('TEXT', 'Text'),
                    ('NUMBER', 'Number'),
                    ('SWITCH', 'Switch'),
                    ('RADIO', 'Radio'),
                ],
                default='SELECT',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='mcpconfigoption',
            name='default_value',
            field=models.JSONField(
                blank=True,
                default=None,
                help_text='Default value. Type depends on field type (str, int, bool, etc.)',
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name='mcpconfigoption',
            name='options',
            field=models.JSONField(
                default=list,
                help_text="For SELECT/RADIO type: [{'name': 'Display', 'value': 'internal'}]",
            ),
        ),
    ]

