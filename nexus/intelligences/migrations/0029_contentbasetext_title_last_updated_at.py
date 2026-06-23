from django.db import migrations, models
from django.db.models import F
from django.db.models.functions import Coalesce
from django.utils import timezone


def backfill_title_and_last_updated_at(apps, schema_editor):
    ContentBaseText = apps.get_model("intelligences", "ContentBaseText")
    now = timezone.now()
    ContentBaseText.objects.filter(title__isnull=True).update(title="Untitled")
    ContentBaseText.objects.filter(last_updated_at__isnull=True).update(
        last_updated_at=Coalesce(F("modified_at"), F("created_at"), now)
    )


class Migration(migrations.Migration):
    dependencies = [
        ("intelligences", "0028_delete_conversationmessage"),
    ]

    operations = [
        migrations.AddField(
            model_name="contentbasetext",
            name="title",
            field=models.CharField(default="Untitled", max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="contentbasetext",
            name="last_updated_at",
            field=models.DateTimeField(null=True),
        ),
        migrations.RunPython(backfill_title_and_last_updated_at, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="contentbasetext",
            name="title",
            field=models.CharField(default="Untitled", max_length=100),
        ),
        migrations.AlterField(
            model_name="contentbasetext",
            name="last_updated_at",
            field=models.DateTimeField(),
        ),
    ]
