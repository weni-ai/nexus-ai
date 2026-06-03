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

    def test_update_creates_category_and_instruction(self):
        request = self.factory.put(
            f"{self.url}",
            {
                "categories": [
                    {
                        "name": "greeting",
                        "instructions": [{"instruction": "Always greet the customer"}],
                    }
                ]
            },
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = ProjectInstructionsViewSet.as_view({"put": "update"})(
            request,
            project_uuid=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response.render()
        content = json.loads(response.content)
        self.assertEqual(content["categories"][0]["name"], "greeting")
        self.assertEqual(len(content["categories"][0]["instructions"]), 1)

        category = InstructionCategory.objects.get(content_base=self.content_base, name="greeting")
        instruction = ContentBaseInstruction.objects.get(category=category)
        self.assertEqual(instruction.instruction, "Always greet the customer")

    def test_update_removes_category_not_in_payload(self):
        InstructionCategory.objects.create(content_base=self.content_base, name="legacy")

        request = self.factory.put(
            f"{self.url}",
            {"categories": [{"name": "greeting", "instructions": []}]},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = ProjectInstructionsViewSet.as_view({"put": "update"})(
            request,
            project_uuid=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(InstructionCategory.objects.filter(content_base=self.content_base, name="legacy").exists())

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
