import django.db.models.deletion
from django.db import migrations, models


def reset_existing_instructions_to_uncategorized(apps, schema_editor):
    ContentBaseInstruction = apps.get_model("intelligences", "ContentBaseInstruction")
    ContentBaseInstruction.objects.all().update(suggested_category="")


class Migration(migrations.Migration):
    dependencies = [
        ("intelligences", "0031_contentbaseinstruction_suggested_category"),
    ]

    operations = [
        migrations.CreateModel(
            name="InstructionCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                (
                    "content_base",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="instruction_categories",
                        to="intelligences.contentbase",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="instructioncategory",
            constraint=models.UniqueConstraint(
                fields=("content_base", "name"),
                name="unique_instruction_category_per_content_base",
            ),
        ),
        migrations.AddField(
            model_name="contentbaseinstruction",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="instructions",
                to="intelligences.instructioncategory",
            ),
        ),
        migrations.RunPython(
            reset_existing_instructions_to_uncategorized,
            migrations.RunPython.noop,
        ),
    ]
