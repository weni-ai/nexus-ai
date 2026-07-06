import csv
import io
from unittest import mock

from django.test import TestCase

from nexus.intelligences.models import ContentBaseInstruction, InstructionCategory
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project
from nexus.usecases.intelligences.instructions import (
    DuplicateCategoryNameError,
    ProjectInstructionsUseCase,
    build_initial_retail_instruction_payload,
    build_instruction_create_payload,
    resolve_retail_instructions,
)
from nexus.usecases.intelligences.tests.intelligence_factory import (
    ContentBaseFactory,
    ContentBaseInstructionFactory,
    IntegratedIntelligenceFactory,
)


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

        csv_content = self.use_case.build_instructions_csv(
            self.content_base,
            category_column="Categoria",
            instruction_column="Instrução",
            uncategorized_label="Sem categoria",
            default_label="Instruções padrão",
        )
        rows = list(csv.reader(io.StringIO(csv_content)))

        self.assertEqual(rows[0], ["Categoria", "Instrução"])
        self.assertEqual(
            rows[1:],
            [
                ["greeting", "Always greet the customer"],
                ["Sem categoria", "Legacy instruction"],
            ],
        )

    def test_build_instructions_csv_includes_default_instructions(self):
        csv_content = self.use_case.build_instructions_csv(
            self.content_base,
            category_column="Categoria",
            instruction_column="Instrução",
            uncategorized_label="Sem categoria",
            default_label="Instruções padrão",
            default_instructions=["Default instruction"],
        )
        rows = list(csv.reader(io.StringIO(csv_content)))

        self.assertEqual(
            rows,
            [["Categoria", "Instrução"], ["Instruções padrão", "Default instruction"]],
        )

    def test_build_instructions_csv_returns_header_only_when_no_instructions(self):
        csv_content = self.use_case.build_instructions_csv(
            self.content_base,
            category_column="Categoria",
            instruction_column="Instrução",
            uncategorized_label="Sem categoria",
            default_label="Instruções padrão",
        )
        rows = list(csv.reader(io.StringIO(csv_content)))

        self.assertEqual(rows, [["Categoria", "Instrução"]])

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

    def test_create_instruction_raises_when_category_name_already_exists(self):
        InstructionCategory.objects.create(content_base=self.content_base, name="greeting")

        with self.assertRaises(DuplicateCategoryNameError):
            self.use_case.create_instruction(
                content_base=self.content_base,
                instruction_text="Always greet the customer",
                category_data={"name": "greeting"},
                user=self.user,
                project_uuid=str(self.project.uuid),
            )

    def test_patch_reuses_existing_category_by_name_without_error(self):
        InstructionCategory.objects.create(content_base=self.content_base, name="policy")
        existing = ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            instruction="Uncategorized instruction",
        )

        self.use_case.patch_grouped_instructions(
            content_base=self.content_base,
            categories_data=[
                {
                    "name": "policy",
                    "instructions": [{"id": existing.id, "instruction": "Uncategorized instruction"}],
                }
            ],
            uncategorized_data=None,
            user=self.user,
            project_uuid=str(self.project.uuid),
        )

        self.assertEqual(InstructionCategory.objects.filter(content_base=self.content_base).count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.category.name, "policy")

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


class TestResolveRetailInstructions(TestCase):
    @mock.patch("nexus.usecases.intelligences.instructions.settings.DEFAULT_RETAIL_INSTRUCTIONS", ["default one"])
    def test_returns_request_instructions_when_provided(self):
        result = resolve_retail_instructions(["custom one", "custom two"])

        self.assertEqual(result, ["custom one", "custom two"])

    @mock.patch("nexus.usecases.intelligences.instructions.settings.DEFAULT_RETAIL_INSTRUCTIONS", ["default one"])
    def test_returns_settings_when_request_instructions_not_provided(self):
        result = resolve_retail_instructions(None)

        self.assertEqual(result, ["default one"])

    @mock.patch("nexus.usecases.intelligences.instructions.settings.DEFAULT_RETAIL_INSTRUCTIONS", ["default one"])
    def test_returns_empty_list_when_request_instructions_is_empty(self):
        result = resolve_retail_instructions([])

        self.assertEqual(result, [])


class TestBuildInstructionCreatePayload(TestCase):
    def test_builds_instruction_objects(self):
        result = build_instruction_create_payload(["first", "second"])

        self.assertEqual(
            result,
            [{"instruction": "first"}, {"instruction": "second"}],
        )


class TestBuildInitialRetailInstructionPayload(TestCase):
    @mock.patch("nexus.usecases.intelligences.instructions.settings.DEFAULT_RETAIL_INSTRUCTIONS", ["default one"])
    def test_returns_empty_list_when_content_base_already_has_instructions(self):
        content_base = ContentBaseFactory()
        ContentBaseInstructionFactory(content_base=content_base)

        result = build_initial_retail_instruction_payload(content_base, ["custom one"])

        self.assertEqual(result, [])

    @mock.patch("nexus.usecases.intelligences.instructions.settings.DEFAULT_RETAIL_INSTRUCTIONS", ["default one"])
    def test_uses_settings_when_content_base_has_no_instructions(self):
        content_base = ContentBaseFactory()
        content_base.instructions.all().delete()

        result = build_initial_retail_instruction_payload(content_base, None)

        self.assertEqual(result, [{"instruction": "default one"}])

    @mock.patch("nexus.usecases.intelligences.instructions.settings.DEFAULT_RETAIL_INSTRUCTIONS", ["default one"])
    def test_uses_request_instructions_when_content_base_has_no_instructions(self):
        content_base = ContentBaseFactory()
        content_base.instructions.all().delete()

        result = build_initial_retail_instruction_payload(content_base, ["custom one", "custom two"])

        self.assertEqual(
            result,
            [{"instruction": "custom one"}, {"instruction": "custom two"}],
        )
