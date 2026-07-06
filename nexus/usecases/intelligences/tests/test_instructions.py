import csv
import io

from django.test import TestCase

from nexus.intelligences.models import ContentBaseInstruction, InstructionCategory
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project
from nexus.usecases.intelligences.instructions import ProjectInstructionsUseCase
from nexus.usecases.intelligences.tests.intelligence_factory import IntegratedIntelligenceFactory


class TestProjectInstructionsUseCase(TestCase):
    def setUp(self):
        integrated_intelligence = IntegratedIntelligenceFactory()
        self.project = integrated_intelligence.project
        self.user = self.project.created_by
        self.content_base = get_default_content_base_by_project(str(self.project.uuid))
        self.use_case = ProjectInstructionsUseCase()

    def test_get_grouped_instructions_includes_uncategorized_instructions(self):
        category = InstructionCategory.objects.create(content_base=self.content_base, name="greeting")
        ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            category=category,
            instruction="Greeting instruction",
        )
        ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            instruction="Legacy instruction",
        )

        payload = self.use_case.get_grouped_instructions(self.content_base)

        self.assertEqual(len(payload["categories"]), 1)
        self.assertEqual(len(payload["uncategorized_instructions"]), 1)
        self.assertEqual(payload["uncategorized_instructions"][0]["instruction"], "Legacy instruction")

    def test_build_instructions_csv_exports_flat_instruction_list(self):
        greeting = InstructionCategory.objects.create(content_base=self.content_base, name="greeting")
        InstructionCategory.objects.create(content_base=self.content_base, name="policy")
        ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            category=greeting,
            instruction="Always greet the customer",
        )
        ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            instruction="Legacy instruction",
        )

        csv_content = self.use_case.build_instructions_csv(self.content_base)
        rows = list(csv.reader(io.StringIO(csv_content)))

        self.assertEqual(rows[0], ["category", "instruction"])
        self.assertEqual(
            rows[1:],
            [
                ["greeting", "Always greet the customer"],
                ["", "Legacy instruction"],
            ],
        )

    def test_build_instructions_csv_returns_header_only_when_no_instructions(self):
        csv_content = self.use_case.build_instructions_csv(self.content_base)
        rows = list(csv.reader(io.StringIO(csv_content)))

        self.assertEqual(rows, [["category", "instruction"]])

    def test_create_instruction_uncategorized(self):
        self.use_case.create_instruction(
            content_base=self.content_base,
            instruction_text="Legacy instruction",
            category_data=None,
            user=self.user,
            project_uuid=str(self.project.uuid),
        )

        instruction = ContentBaseInstruction.objects.get(
            content_base=self.content_base,
            instruction="Legacy instruction",
        )
        self.assertIsNone(instruction.category_id)

    def test_create_instruction_with_new_category_name(self):
        self.use_case.create_instruction(
            content_base=self.content_base,
            instruction_text="Always greet the customer",
            category_data={"name": "greeting"},
            user=self.user,
            project_uuid=str(self.project.uuid),
        )

        category = InstructionCategory.objects.get(content_base=self.content_base, name="greeting")
        self.assertEqual(category.instructions.count(), 1)

    def test_patch_updates_instruction_without_creating(self):
        category = InstructionCategory.objects.create(content_base=self.content_base, name="greeting")
        existing = ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            category=category,
            instruction="Existing instruction",
        )

        self.use_case.patch_grouped_instructions(
            content_base=self.content_base,
            categories_data=[
                {
                    "id": category.id,
                    "instructions": [{"id": existing.id, "instruction": "Updated instruction"}],
                }
            ],
            uncategorized_data=None,
            user=self.user,
            project_uuid=str(self.project.uuid),
        )

        self.assertEqual(category.instructions.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.instruction, "Updated instruction")

    def test_patch_creates_category_by_name_and_assigns_instruction(self):
        existing = ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            instruction="Legacy instruction",
        )

        self.use_case.patch_grouped_instructions(
            content_base=self.content_base,
            categories_data=[
                {
                    "name": "greeting",
                    "instructions": [{"id": existing.id, "instruction": "Legacy instruction"}],
                }
            ],
            uncategorized_data=None,
            user=self.user,
            project_uuid=str(self.project.uuid),
        )

        category = InstructionCategory.objects.get(content_base=self.content_base, name="greeting")
        existing.refresh_from_db()
        self.assertEqual(existing.category_id, category.id)
        self.assertEqual(existing.suggested_category, "greeting")

    def test_delete_category_moves_instructions_to_uncategorized(self):
        category = InstructionCategory.objects.create(content_base=self.content_base, name="greeting")
        instruction = ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            category=category,
            instruction="Greeting instruction",
            suggested_category="greeting",
        )

        payload = self.use_case.delete_category(
            content_base=self.content_base,
            category_id=category.id,
            project_uuid=str(self.project.uuid),
        )

        instruction.refresh_from_db()
        self.assertIsNone(instruction.category_id)
        self.assertEqual(instruction.suggested_category, "")
        self.assertEqual(payload["categories"], [])
        self.assertEqual(len(payload["uncategorized_instructions"]), 1)
