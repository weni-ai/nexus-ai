from unittest import mock

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from nexus.projects.models import Project, ProjectGuardrailsConfig
from nexus.projects.permissions import has_project_permission
from nexus.usecases.guardrails.project_guardrails_config import ProjectGuardrailsConfigUseCase
from nexus.usecases.guardrails.tests.guardrail_test_helpers import fake_pool_resolve as _fake_pool_resolve
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class ProjectPromptInjectionFilterAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.url = reverse("project-prompt-injection-filter", kwargs={"project_uuid": str(self.project.uuid)})

        self._patcher = mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
        self._mock_ext_permission = self._patcher.start()

        def _local_permission(request, project_uuid, method):
            try:
                project = Project.objects.get(uuid=project_uuid)
                return has_project_permission(request.user, project, method)
            except Project.DoesNotExist:
                return False

        self._mock_ext_permission.side_effect = _local_permission
        self.client.force_authenticate(user=self.user)

        self._pool_patcher = mock.patch(
            "nexus.usecases.guardrails.project_guardrails_config.BedrockGuardrailPoolService.get_or_create_pool",
            side_effect=_fake_pool_resolve,
        )
        self._mock_get_or_create_pool = self._pool_patcher.start()

    def tearDown(self):
        self._pool_patcher.stop()
        self._patcher.stop()

    def test_get_defaults_to_disabled(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["enabled"])
        self.assertTrue(response.data["writable"])
        self.assertTrue(ProjectGuardrailsConfig.objects.filter(project=self.project).exists())

    def test_patch_enables_without_bedrock_pool(self):
        ProjectGuardrailsConfigUseCase.get_or_initialize(self.project)
        ProjectGuardrailsConfig.objects.filter(project=self.project).update(
            category_states=ProjectGuardrailsConfigUseCase.build_default_category_states(blocked=False),
            bedrock_guardrail_pool=None,
            bedrock_guardrail_identifier=None,
            bedrock_guardrail_version=None,
            prompt_injection_filter_enabled=False,
        )
        self._mock_get_or_create_pool.reset_mock()

        response = self.client.patch(self.url, {"enabled": True}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["enabled"])
        config = ProjectGuardrailsConfig.objects.get(project=self.project)
        self.assertTrue(config.prompt_injection_filter_enabled)
        self.assertIsNone(config.bedrock_guardrail_identifier)
        self._mock_get_or_create_pool.assert_not_called()

    def test_patch_requires_enabled(self):
        response = self.client.patch(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
