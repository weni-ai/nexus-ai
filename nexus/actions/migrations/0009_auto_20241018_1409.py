# Generated by Django 4.2.10 on 2024-10-18 14:09

from django.db import migrations


def gen_uuid(apps, schema_editor):
    MyModel = apps.get_model("actions", "flow")
    for row in MyModel.objects.all():
        row.flow_uuid = row.uuid
        row.save(update_fields=["flow_uuid"])


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0008_flow_action_uuid'),
    ]

    operations = [
    ]
