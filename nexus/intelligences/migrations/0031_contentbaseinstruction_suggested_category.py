from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("intelligences", "0030_alter_contentbasetext_last_updated_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="contentbaseinstruction",
            name="suggested_category",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
