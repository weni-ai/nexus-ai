import csv
import io
import json
from unittest import mock

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.intelligences.api.instruction_views import ProjectInstructionsViewSet
from nexus.intelligences.models import ContentBaseInstruction, InstructionCategory
from nexus.projects.models import Project
from nexus.projects.permissions import has_project_permission
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project
from nexus.usecases.intelligences.tests.intelligence_factory import IntegratedIntelligenceFactory


class TestProjectInstructionsViewSet(TestCase):
    def setUp(self):
        integrated_intelligence = IntegratedIntelligenceFactory()
        self.project = integrated_intelligence.project
        self.user = self.project.created_by
        self.content_base = get_default_content_base_by_project(str(self.project.uuid))
        self.factory = APIRequestFactory()
        self.url = f"{self.project.uuid}/instructions/"

        self._patcher = mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
        self._mock_ext_permission = self._patcher.start()

        def _local_permission(request, project_uuid, method):
            try:
                project = Project.objects.get(uuid=project_uuid)
                return has_project_permission(request.user, project, method)
            except Project.DoesNotExist:
                return False

        self._mock_ext_permission.side_effect = _local_permission

        self._feature_flag_patcher = mock.patch(
            "nexus.feature_flags.permissions.is_feature_active_for_attributes",
            return_value=True,
        )
        self._feature_flag_patcher.start()

    def tearDown(self):
        self._feature_flag_patcher.stop()
        self._patcher.stop()

    def _post(self, data):
        request = self.factory.post(f"{self.url}", data, format="json")
        force_authenticate(request, user=self.user)
        return ProjectInstructionsViewSet.as_view({"post": "create"})(
            request,
            project_uuid=str(self.project.uuid),
        )

    def _patch(self, data):
        request = self.factory.patch(f"{self.url}", data, format="json")
        force_authenticate(request, user=self.user)
        return ProjectInstructionsViewSet.as_view({"patch": "partial_update"})(
            request,
            project_uuid=str(self.project.uuid),
        )

    def test_list_returns_grouped_categories_including_empty_category(self):
        greeting = InstructionCategory.objects.create(content_base=self.content_base, name="greeting")
        InstructionCategory.objects.create(content_base=self.content_base, name="policy")
        ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            category=greeting,
            instruction="Always greet the customer",
        )

        request = self.factory.get(f"{self.url}")
        force_authenticate(request, user=self.user)
        response = ProjectInstructionsViewSet.as_view({"get": "list"})(
            request,
            project_uuid=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response.render()
        content = json.loads(response.content)

        self.assertEqual(len(content["categories"]), 2)
        self.assertEqual(content["categories"][0]["name"], "greeting")
        self.assertEqual(len(content["categories"][0]["instructions"]), 1)
        self.assertEqual(content["categories"][1]["name"], "policy")
        self.assertEqual(content["categories"][1]["instructions"], [])

    def test_post_creates_instruction_in_new_category_by_name(self):
        response = self._post(
            {
                "instruction": "Always greet the customer",
                "category": {"name": "greeting"},
            }
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response.render()
        content = json.loads(response.content)
        self.assertEqual(content["categories"][0]["name"], "greeting")
        self.assertEqual(len(content["categories"][0]["instructions"]), 1)

        category = InstructionCategory.objects.get(content_base=self.content_base, name="greeting")
        instruction = ContentBaseInstruction.objects.get(category=category)
        self.assertEqual(instruction.instruction, "Always greet the customer")

    def test_post_creates_uncategorized_instruction_when_category_omitted(self):
        response = self._post({"instruction": "Legacy instruction without category"})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        instruction = ContentBaseInstruction.objects.get(
            content_base=self.content_base,
            instruction="Legacy instruction without category",
        )
        self.assertIsNone(instruction.category_id)

        response.render()
        content = json.loads(response.content)
        self.assertEqual(len(content["uncategorized_instructions"]), 1)

    def test_post_creates_instruction_in_existing_category_by_id(self):
        category = InstructionCategory.objects.create(content_base=self.content_base, name="policy")

        response = self._post(
            {
                "instruction": "Never promise refunds without approval",
                "category": {"id": category.id},
            }
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(category.instructions.count(), 1)

    def test_post_returns_404_for_unknown_category_id(self):
        response = self._post(
            {
                "instruction": "Some instruction",
                "category": {"id": 99999},
            }
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_updates_instruction_without_creating(self):
        category = InstructionCategory.objects.create(content_base=self.content_base, name="greeting")
        existing = ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            category=category,
            instruction="Old text",
        )

        response = self._patch(
            {
                "categories": [
                    {
                        "id": category.id,
                        "instructions": [{"id": existing.id, "instruction": "Updated text"}],
                    }
                ]
            }
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(category.instructions.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.instruction, "Updated text")

    def test_patch_creates_category_by_name_and_moves_uncategorized_instruction(self):
        existing = ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            instruction="When a user asks for a human agent",
        )

        response = self._patch(
            {
                "categories": [
                    {
                        "name": "PERSONALIDADE",
                        "instructions": [{"id": existing.id, "instruction": "When a user asks for a human agent"}],
                    }
                ]
            }
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        category = InstructionCategory.objects.get(content_base=self.content_base, name="PERSONALIDADE")
        existing.refresh_from_db()
        self.assertEqual(existing.category_id, category.id)
        self.assertEqual(existing.suggested_category, "PERSONALIDADE")

        response.render()
        content = json.loads(response.content)
        self.assertEqual(content["categories"][0]["name"], "PERSONALIDADE")
        self.assertNotIn("uncategorized_instructions", content)

    def test_patch_uses_existing_category_by_name(self):
        category = InstructionCategory.objects.create(content_base=self.content_base, name="policy")
        existing = ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            instruction="Uncategorized instruction",
        )

        response = self._patch(
            {
                "categories": [
                    {
                        "name": "policy",
                        "instructions": [{"id": existing.id, "instruction": "Uncategorized instruction"}],
                    }
                ]
            }
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(InstructionCategory.objects.filter(content_base=self.content_base).count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.category_id, category.id)

    def test_patch_rejects_category_without_id_or_name(self):
        response = self._patch(
            {
                "categories": [
                    {
                        "instructions": [{"id": 1, "instruction": "Always greet the customer"}],
                    }
                ]
            }
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_rejects_instruction_without_id(self):
        response = self._patch(
            {
                "categories": [
                    {
                        "name": "greeting",
                        "instructions": [{"instruction": "Always greet the customer"}],
                    }
                ]
            }
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_leaves_other_categories_unchanged(self):
        legacy = InstructionCategory.objects.create(content_base=self.content_base, name="legacy")
        greeting = InstructionCategory.objects.create(content_base=self.content_base, name="greeting")
        instruction = ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            category=greeting,
            instruction="Greeting instruction",
        )

        response = self._patch(
            {
                "categories": [
                    {
                        "id": greeting.id,
                        "instructions": [{"id": instruction.id, "instruction": "Updated greeting"}],
                    }
                ]
            }
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(InstructionCategory.objects.filter(id=legacy.id).exists())

    def test_patch_empty_body_returns_400(self):
        response = self._patch({})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_export_returns_csv_with_all_instructions(self):
        greeting = InstructionCategory.objects.create(content_base=self.content_base, name="greeting")
        ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            category=greeting,
            instruction="Always greet the customer",
        )
        ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            instruction="Legacy instruction",
        )

        export_url = f"{self.project.uuid}/instructions/export/"
        request = self.factory.get(export_url)
        force_authenticate(request, user=self.user)
        response = ProjectInstructionsViewSet.as_view({"get": "export"})(
            request,
            project_uuid=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(f"instructions_{self.project.uuid}.csv", response["Content-Disposition"])

        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8"))))
        self.assertEqual(rows[0], ["category", "instruction"])
        self.assertEqual(
            rows[1:],
            [
                ["greeting", "Always greet the customer"],
                ["", "Legacy instruction"],
            ],
        )

    def test_export_accepts_text_csv_accept_header(self):
        export_url = f"{self.project.uuid}/instructions/export/"
        request = self.factory.get(export_url, HTTP_ACCEPT="text/csv")
        force_authenticate(request, user=self.user)
        response = ProjectInstructionsViewSet.as_view({"get": "export"})(
            request,
            project_uuid=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")

    def test_export_returns_header_only_when_no_instructions(self):
        export_url = f"{self.project.uuid}/instructions/export/"
        request = self.factory.get(export_url)
        force_authenticate(request, user=self.user)
        response = ProjectInstructionsViewSet.as_view({"get": "export"})(
            request,
            project_uuid=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8"))))
        self.assertEqual(rows, [["category", "instruction"]])

    @mock.patch("nexus.feature_flags.permissions.is_feature_active_for_attributes", return_value=False)
    def test_export_returns_403_when_feature_flag_is_inactive(self, _mock_feature_flag):
        export_url = f"{self.project.uuid}/instructions/export/"
        request = self.factory.get(export_url)
        force_authenticate(request, user=self.user)
        response = ProjectInstructionsViewSet.as_view({"get": "export"})(
            request,
            project_uuid=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @mock.patch("nexus.feature_flags.permissions.is_feature_active_for_attributes", return_value=False)
    def test_list_returns_403_when_feature_flag_is_inactive(self, _mock_feature_flag):
        request = self.factory.get(f"{self.url}")
        force_authenticate(request, user=self.user)
        response = ProjectInstructionsViewSet.as_view({"get": "list"})(
            request,
            project_uuid=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_destroy_deletes_instruction_and_returns_grouped_payload(self):
        category = InstructionCategory.objects.create(content_base=self.content_base, name="greeting")
        instruction = ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            category=category,
            instruction="Always greet the customer",
        )

        request = self.factory.delete(f"{self.url}?id={instruction.id}")
        force_authenticate(request, user=self.user)
        response = ProjectInstructionsViewSet.as_view({"delete": "destroy"})(
            request,
            project_uuid=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(ContentBaseInstruction.objects.filter(id=instruction.id).exists())
        response.render()
        content = json.loads(response.content)
        self.assertEqual(content["categories"][0]["instructions"], [])

    def test_destroy_category_moves_instructions_to_uncategorized(self):
        category = InstructionCategory.objects.create(content_base=self.content_base, name="greeting")
        instruction = ContentBaseInstruction.objects.create(
            content_base=self.content_base,
            category=category,
            instruction="Always greet the customer",
            suggested_category="greeting",
        )
        category_url = f"{self.project.uuid}/instructions/categories/{category.id}/"

        request = self.factory.delete(category_url)
        force_authenticate(request, user=self.user)
        response = ProjectInstructionsViewSet.as_view({"delete": "destroy_category"})(
            request,
            project_uuid=str(self.project.uuid),
            category_id=category.id,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(InstructionCategory.objects.filter(id=category.id).exists())
        instruction.refresh_from_db()
        self.assertIsNone(instruction.category_id)
        self.assertEqual(instruction.suggested_category, "")

        response.render()
        content = json.loads(response.content)
        self.assertEqual(content["categories"], [])
        self.assertEqual(len(content["uncategorized_instructions"]), 1)
        self.assertEqual(content["uncategorized_instructions"][0]["instruction"], "Always greet the customer")

    def test_destroy_category_returns_404_for_unknown_category(self):
        request = self.factory.delete(f"{self.project.uuid}/instructions/categories/99999/")
        force_authenticate(request, user=self.user)
        response = ProjectInstructionsViewSet.as_view({"delete": "destroy_category"})(
            request,
            project_uuid=str(self.project.uuid),
            category_id=99999,
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
