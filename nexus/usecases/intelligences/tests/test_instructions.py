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
