import json
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.intelligences.api.views import InstructionsClassificationAPIView
from nexus.intelligences.models import ContentBaseInstruction
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project
from nexus.usecases.intelligences.tests.intelligence_factory import (
    ContentBaseFactory,
    IntegratedIntelligenceFactory,
)
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class TestInstructionsClassificationAPIView(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.content_base = ContentBaseFactory(is_router=True)
        self.org = self.content_base.intelligence.org
        self.user = self.org.created_by
        self.project = ProjectFactory(
            brain_on=True,
            name=self.content_base.intelligence.name,
            org=self.org,
            created_by=self.user,
        )
        self.project.authorizations.update_or_create(user=self.user, defaults={"role": 3})
        IntegratedIntelligenceFactory(
            intelligence=self.content_base.intelligence,
            project=self.project,
            created_by=self.user,
        )
        self.content_base.intelligence.is_router = True
        self.content_base.intelligence.description = "Project description for classification"
        self.content_base.intelligence.save(update_fields=["description", "is_router"])

        self.url = f"{self.project.uuid}/instructions-classification/"

        self._patcher = mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
        self._mock_ext_permission = self._patcher.start()

        def _local_permission(request, project_uuid, method):
            from nexus.projects.models import Project
            from nexus.projects.permissions import has_project_permission

            project = Project.objects.get(uuid=project_uuid)
            return has_project_permission(request.user, project, method)

        self._mock_ext_permission.side_effect = _local_permission

        self._lambda_patcher = mock.patch("nexus.usecases.intelligences.lambda_usecase.LambdaUseCase")
        self._mock_lambda_class = self._lambda_patcher.start()
        self._mock_instruction_classify = self._mock_lambda_class.return_value.instruction_classify
        self._mock_instruction_classify_legacy = self._mock_lambda_class.return_value.instruction_classify_legacy
        self._mock_instruction_classify.return_value = (
            [{"name": "policy", "reason": "Matches policy rules"}],
            "Improve clarity",
            "policy",
        )
        self._mock_instruction_classify_legacy.return_value = (
            [{"name": "duplicate", "reason": "Duplicate instruction"}],
            "Legacy suggestion",
        )

        self._feature_flag_patcher = mock.patch(
            "nexus.intelligences.api.views.is_feature_active_for_attributes",
            return_value=True,
        )
        self._feature_flag_patcher.start()

    def tearDown(self):
        self._feature_flag_patcher.stop()
        self._lambda_patcher.stop()
        self._patcher.stop()

    def test_post_passes_project_description_and_categories_to_lambda_when_flag_active(self):
        request = self.factory.post(
            self.url,
            {
                "instruction": "Always greet the customer",
                "instructions_categories": ["policy", "greeting"],
                "language": "en",
            },
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = InstructionsClassificationAPIView.as_view()(request, project_uuid=str(self.project.uuid))

        self.assertEqual(response.status_code, 200, response.data)
        response.render()
        content = json.loads(response.content)
        self.assertEqual(content["classification"], [{"name": "policy", "reason": "Matches policy rules"}])
        self.assertEqual(content["suggested_category"], "policy")
        self.assertEqual(content["suggestion"], "Improve clarity")

        content_base = get_default_content_base_by_project(str(self.project.uuid))
        self._mock_instruction_classify.assert_called_once_with(
            name=mock.ANY,
            occupation=mock.ANY,
            goal=mock.ANY,
            adjective=mock.ANY,
            instructions=mock.ANY,
            instruction_to_classify="Always greet the customer",
            instructions_categories=["policy", "greeting"],
            language="en",
            project_description=content_base.intelligence.description,
        )
        self._mock_instruction_classify_legacy.assert_not_called()

    def test_post_returns_empty_suggested_category_when_lambda_returns_empty_string(self):
        self._mock_instruction_classify.return_value = ([], None, "")

        request = self.factory.post(
            self.url,
            {
                "instruction": "Always greet the customer",
                "instructions_categories": [],
                "language": "en",
            },
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = InstructionsClassificationAPIView.as_view()(request, project_uuid=str(self.project.uuid))

        self.assertEqual(response.status_code, 200, response.data)
        response.render()
        content = json.loads(response.content)
        self.assertEqual(content["suggested_category"], "")

    @mock.patch("nexus.intelligences.api.views.is_feature_active_for_attributes", return_value=False)
    def test_post_uses_legacy_path_when_feature_flag_is_inactive(self, _mock_is_feature_active):
        request = self.factory.post(
            self.url,
            {
                "instruction": "Always greet the customer",
                "instructions_categories": ["policy"],
                "language": "en",
            },
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = InstructionsClassificationAPIView.as_view()(request, project_uuid=str(self.project.uuid))

        self.assertEqual(response.status_code, 200, response.data)
        response.render()
        content = json.loads(response.content)
        self.assertEqual(
            content["classification"],
            [{"name": "duplicate", "reason": "Duplicate instruction"}],
        )
        self.assertEqual(content["suggestion"], "Legacy suggestion")
        self.assertNotIn("suggested_category", content)

        self._mock_instruction_classify_legacy.assert_called_once_with(
            name=mock.ANY,
            occupation=mock.ANY,
            goal=mock.ANY,
            adjective=mock.ANY,
            instructions=mock.ANY,
            instruction_to_classify="Always greet the customer",
            language="en",
        )
        self._mock_instruction_classify.assert_not_called()

    def test_post_accepts_request_without_instructions_categories_when_flag_active(self):
        request = self.factory.post(
            self.url,
            {
                "instruction": "Always greet the customer",
                "language": "en",
            },
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = InstructionsClassificationAPIView.as_view()(request, project_uuid=str(self.project.uuid))

        self.assertEqual(response.status_code, 200, response.data)
        self._mock_instruction_classify.assert_called_once()
        call_kwargs = self._mock_instruction_classify.call_args.kwargs
        self.assertEqual(call_kwargs["instructions_categories"], [])

    def test_post_excludes_instruction_id_from_lambda_comparison_on_revalidate(self):
        content_base = get_default_content_base_by_project(str(self.project.uuid))
        content_base.instructions.all().delete()
        existing = ContentBaseInstruction.objects.create(
            content_base=content_base,
            instruction="Don't talk about things that are outside your scope.",
        )
        ContentBaseInstruction.objects.create(
            content_base=content_base,
            instruction="Always greet the customer",
        )

        request = self.factory.post(
            self.url,
            {
                "instruction": "Don't talk about things that are outside your scope.",
                "instruction_id": existing.id,
                "instructions_categories": ["policy", "greeting"],
                "language": "en",
            },
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = InstructionsClassificationAPIView.as_view()(request, project_uuid=str(self.project.uuid))

        self.assertEqual(response.status_code, 200, response.data)
        call_kwargs = self._mock_instruction_classify.call_args.kwargs
        self.assertEqual(
            call_kwargs["instructions"],
            [{"instruction": "Always greet the customer", "type": "custom"}],
        )

    def test_post_returns_404_for_unknown_instruction_id(self):
        request = self.factory.post(
            self.url,
            {
                "instruction": "Always greet the customer",
                "instruction_id": 99999,
                "language": "en",
            },
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = InstructionsClassificationAPIView.as_view()(request, project_uuid=str(self.project.uuid))

        self.assertEqual(response.status_code, 404, response.data)
        self._mock_instruction_classify.assert_not_called()
