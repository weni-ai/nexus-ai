from django.db import migrations, models
import django.db.models.deletion


def migrate_suggested_categories_to_instruction_categories(apps, schema_editor):
    ContentBaseInstruction = apps.get_model("intelligences", "ContentBaseInstruction")
    InstructionCategory = apps.get_model("intelligences", "InstructionCategory")

    for instruction in ContentBaseInstruction.objects.exclude(suggested_category="").iterator():
        category_name = instruction.suggested_category.strip()
        if not category_name:
            continue

        category, _ = InstructionCategory.objects.get_or_create(
            content_base_id=instruction.content_base_id,
            name=category_name,
        )
        instruction.category_id = category.id
        instruction.save(update_fields=["category_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("intelligences", "0029_contentbaseinstruction_suggested_category"),
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
                on_delete=django.db.models.deletion.CASCADE,
                related_name="instructions",
                to="intelligences.instructioncategory",
            ),
        ),
        migrations.RunPython(
            migrate_suggested_categories_to_instruction_categories,
            migrations.RunPython.noop,
        ),
    ]
