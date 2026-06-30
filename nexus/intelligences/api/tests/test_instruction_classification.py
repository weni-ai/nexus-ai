import json
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.intelligences.api.views import InstructionsClassificationAPIView
from nexus.intelligences.models import ContentBaseAgent
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
        self.user.name = "vanessa.souza"
        self.user.occupation = "Platform Admin"

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
        self.content_base.intelligence.save(update_fields=["is_router"])

        content_base = get_default_content_base_by_project(str(self.project.uuid))
        self.agent, _ = ContentBaseAgent.objects.update_or_create(
            content_base=content_base,
            defaults={
                "name": "Especialista STIHL",
                "role": "Assistente inteligente",
                "personality": "Amigável",
                "goal": "Responder perguntas dos clientes e vender produtos.",
            },
        )

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
        self._mock_instruction_classify.return_value = ([], "Improve clarity")

    def tearDown(self):
        self._lambda_patcher.stop()
        self._patcher.stop()

    def _post_classify(self, instruction="Always greet the customer"):
        request = self.factory.post(
            self.url,
            {"instruction": instruction, "language": "pt-br"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        return InstructionsClassificationAPIView.as_view()(request, project_uuid=str(self.project.uuid))

    def test_passes_agent_identity_not_user_identity_to_lambda(self):
        response = self._post_classify(
            instruction="Você sempre se apresenta e se refere a si mesmo no gênero masculino."
        )

        self.assertEqual(response.status_code, 200, response.data)
        self._mock_instruction_classify.assert_called_once()
        call_kwargs = self._mock_instruction_classify.call_args.kwargs

        self.assertEqual(call_kwargs["name"], "Especialista STIHL")
        self.assertEqual(call_kwargs["occupation"], "Assistente inteligente")
        self.assertEqual(call_kwargs["goal"], "Responder perguntas dos clientes e vender produtos.")
        self.assertEqual(call_kwargs["adjective"], "Amigável")
        self.assertNotEqual(call_kwargs["name"], "vanessa.souza")
        self.assertNotEqual(call_kwargs["occupation"], "Platform Admin")

    def test_uses_defaults_when_agent_profile_fields_are_empty(self):
        self.agent.name = None
        self.agent.role = None
        self.agent.save(update_fields=["name", "role"])

        response = self._post_classify()

        self.assertEqual(response.status_code, 200, response.data)
        call_kwargs = self._mock_instruction_classify.call_args.kwargs
        self.assertEqual(call_kwargs["name"], "Agent")
        self.assertEqual(call_kwargs["occupation"], "Customer Service Agent")

    def test_returns_lambda_classification_response(self):
        self._mock_instruction_classify.return_value = (
            [{"name": "Conflitos", "reason": "Potential conflict with existing instructions"}],
            "Clarify the instruction scope",
        )

        response = self._post_classify()

        self.assertEqual(response.status_code, 200, response.data)
        response.render()
        content = json.loads(response.content)
        self.assertEqual(
            content["classification"],
            [{"name": "Conflitos", "reason": "Potential conflict with existing instructions"}],
        )
        self.assertEqual(content["suggestion"], "Clarify the instruction scope")
