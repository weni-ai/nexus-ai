from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("intelligences", "0028_delete_conversationmessage"),
    ]

    operations = [
        migrations.AddField(
            model_name="contentbaseinstruction",
            name="suggested_category",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
