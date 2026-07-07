import json
from unittest import mock

import requests
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APIRequestFactory

from nexus.events import notify_async_sync
from nexus.usecases.projects.tests.project_factory import ProjectAuthFactory, ProjectFactory
from nexus.usecases.users.tests.user_factory import UserFactory
from router.repositories.mocks import MockCacheRepository
from router.services.cache_service import CacheService

_TEST_ERROR_MESSAGES = {
    "en-us": "Sorry, I was unable to process your request. Try again.",
    "pt-br": "Não foi possível processar sua solicitação. Tente novamente.",
    "es": "No fue posible procesar su solicitud. Inténtelo de nuevo.",
}


class MultiAgentViewTestCase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

        patch_notify = mock.patch(
            "nexus.inline_agents.api.views.notify_async",
            side_effect=lambda event, **kwargs: notify_async_sync(event, **kwargs),
        )
        patch_notify.start()
        self.addCleanup(patch_notify.stop)

        self.project = ProjectFactory()
        self.project_2 = ProjectFactory()

        self.user = self.project.created_by
        self.user_weni = UserFactory(email="test@weni.ai")
        self.user_vtex = UserFactory(email="test@vtex.com")
        self.user_inline = self.project_2.created_by

        ProjectAuthFactory(project=self.project, user=self.user_weni)
        ProjectAuthFactory(project=self.project, user=self.user_vtex)
        ProjectAuthFactory(project=self.project_2, user=self.user_weni)
        ProjectAuthFactory(project=self.project_2, user=self.user_vtex)

        # External token for authentication
        self.external_token = "test-external-token"

    def test_get_multi_agent_with_agent_builder_without_access(self):
        # Delete the ProjectAuth record for self.user to simulate no access
        from nexus.projects.models import ProjectAuth

        ProjectAuth.objects.filter(user=self.user, project=self.project).delete()

        client = APIClient()
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project.uuid)})

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = client.get(url, HTTP_AUTHORIZATION=f"Bearer {self.external_token}")

        response.render()
        content = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(content.get("multi_agents"), False)
        # can_view is no longer returned by the view
        self.assertIsNone(content.get("can_view"))

    def test_get_multi_agent_with_agent_builder_with_weni_access(self):
        client = APIClient()
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project.uuid)})

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = client.get(url, HTTP_AUTHORIZATION=f"Bearer {self.external_token}")

        response.render()
        content = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(content.get("multi_agents"), False)
        # can_view is no longer returned by the view
        self.assertIsNone(content.get("can_view"))

    def test_get_multi_agent_with_agent_builder_with_vtex_access(self):
        client = APIClient()
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project.uuid)})

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = client.get(url, HTTP_AUTHORIZATION=f"Bearer {self.external_token}")

        response.render()
        content = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(content.get("multi_agents"), False)
        # can_view is no longer returned by the view
        self.assertIsNone(content.get("can_view"))

    def test_update_multi_agent_with_agent_builder_2_without_access(self):
        # Delete the ProjectAuth record for self.user_inline to simulate no access
        from nexus.projects.models import ProjectAuth

        ProjectAuth.objects.filter(user=self.user_inline, project=self.project_2).delete()

        client = APIClient()
        client.force_authenticate(user=self.user_inline)
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project_2.uuid)})
        response = client.patch(url, {"multi_agents": True}, format="json")
        response.render()
        self.assertEqual(response.status_code, 403)

    def test_update_multi_agent_with_agent_builder_2_with_weni_access(self):
        client = APIClient()
        client.force_authenticate(user=self.user_weni)
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project_2.uuid)})

        # Use a token that's NOT in EXTERNAL_SUPERUSERS_TOKENS to trigger ProjectPermission path
        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", []):
            response = client.patch(
                url, {"multi_agents": True}, format="json", HTTP_AUTHORIZATION="Bearer invalid-token"
            )

        response.render()
        content = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(content.get("multi_agents"), True)

    @mock.patch("nexus.usecases.projects.project_type_update_eda.publish_project_type_update")
    def test_patch_inline_switch_false_to_true_publishes_eda_superuser_token(self, mock_publish):
        client = APIClient()
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project.uuid)})

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", [self.external_token]):
            response = client.patch(
                url, {"multi_agents": True}, format="json", HTTP_AUTHORIZATION=f"Bearer {self.external_token}"
            )

        self.assertEqual(response.status_code, 200)
        mock_publish.assert_called_once_with(
            project_uuid=str(self.project.uuid),
            user_email="",
            is_multi_agents=True,
        )

    @mock.patch("nexus.usecases.projects.project_type_update_eda.publish_project_type_update")
    def test_patch_inline_switch_false_to_true_publishes_eda_with_request_user_email(self, mock_publish):
        client = APIClient()
        client.force_authenticate(user=self.user_weni)
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project.uuid)})

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", []):
            response = client.patch(
                url, {"multi_agents": True}, format="json", HTTP_AUTHORIZATION="Bearer invalid-token"
            )

        self.assertEqual(response.status_code, 200)
        mock_publish.assert_called_once_with(
            project_uuid=str(self.project.uuid),
            user_email=self.user_weni.email,
            is_multi_agents=True,
        )

    @mock.patch("nexus.usecases.projects.project_type_update_eda.publish_project_type_update")
    @mock.patch("nexus.projects.permissions._check_project_authorization")
    def test_patch_inline_switch_publishes_eda_with_project_auth_api_user_email(self, mock_check_auth, mock_publish):
        mock_check_auth.return_value = (True, "identity-from-auth-api@example.com")
        client = APIClient()
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project.uuid)})

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", []):
            response = client.patch(
                url, {"multi_agents": True}, format="json", HTTP_AUTHORIZATION="Bearer project-token"
            )

        self.assertEqual(response.status_code, 200)
        mock_publish.assert_called_once_with(
            project_uuid=str(self.project.uuid),
            user_email="identity-from-auth-api@example.com",
            is_multi_agents=True,
        )

    @mock.patch("nexus.usecases.projects.project_type_update_eda.publish_project_type_update")
    def test_patch_inline_switch_stays_true_does_not_publish_eda_again(self, mock_publish):
        self.project.inline_agent_switch = True
        self.project.save(update_fields=["inline_agent_switch"])

        client = APIClient()
        client.force_authenticate(user=self.user_weni)
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project.uuid)})

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", []):
            response = client.patch(
                url, {"multi_agents": True}, format="json", HTTP_AUTHORIZATION="Bearer invalid-token"
            )

        self.assertEqual(response.status_code, 200)
        mock_publish.assert_not_called()

    @mock.patch("nexus.usecases.projects.project_type_update_eda.publish_project_type_update")
    def test_patch_inline_switch_true_to_false_does_not_publish_eda(self, mock_publish):
        self.project.inline_agent_switch = True
        self.project.save(update_fields=["inline_agent_switch"])

        client = APIClient()
        client.force_authenticate(user=self.user_weni)
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project.uuid)})

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", []):
            response = client.patch(
                url, {"multi_agents": False}, format="json", HTTP_AUTHORIZATION="Bearer invalid-token"
            )

        self.assertEqual(response.status_code, 200)
        mock_publish.assert_not_called()

    @mock.patch("nexus.usecases.projects.project_type_update_eda.publish_project_type_update")
    def test_patch_multi_agents_invalid_type_returns_400(self, mock_publish):
        client = APIClient()
        client.force_authenticate(user=self.user_weni)
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project.uuid)})

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", []):
            response = client.patch(
                url, {"multi_agents": "not-a-boolean"}, format="json", HTTP_AUTHORIZATION="Bearer invalid-token"
            )

        self.assertEqual(response.status_code, 400)
        mock_publish.assert_not_called()

    @mock.patch("nexus.usecases.projects.project_type_update_eda.publish_project_type_update")
    def test_patch_multi_agents_string_false_no_eda_publish(self, mock_publish):
        client = APIClient()
        client.force_authenticate(user=self.user_weni)
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project.uuid)})

        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", []):
            response = client.patch(
                url, {"multi_agents": "false"}, format="json", HTTP_AUTHORIZATION="Bearer invalid-token"
            )

        self.assertEqual(response.status_code, 200)
        mock_publish.assert_not_called()

    def test_update_multi_agent_with_agent_builder_2_with_vtex_access(self):
        client = APIClient()
        client.force_authenticate(user=self.user_vtex)
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project_2.uuid)})

        # Use a token that's NOT in EXTERNAL_SUPERUSERS_TOKENS to trigger ProjectPermission path
        with mock.patch("django.conf.settings.EXTERNAL_SUPERUSERS_TOKENS", []):
            response = client.patch(
                url, {"multi_agents": True}, format="json", HTTP_AUTHORIZATION="Bearer invalid-token"
            )

        response.render()
        content = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(content.get("multi_agents"), True)


class ProjectComponentsViewTestCase(TestCase):
    """Test case for ProjectComponentsView cache invalidation."""

    def setUp(self):
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @mock.patch("nexus.inline_agents.api.views.notify_async")
    @mock.patch("nexus.projects.permissions._check_project_authorization")
    def test_patch_use_components_calls_cache_invalidation(self, mock_check_auth, mock_notify_async):
        """Test that updating use_components triggers cache invalidation event."""
        # Make external auth fail with RequestException to trigger internal permission fallback
        mock_check_auth.side_effect = requests.RequestException("Mocked external auth failure")

        url = reverse("project-components", kwargs={"project_uuid": str(self.project.uuid)})
        response = self.client.patch(url, {"use_components": True}, format="json")

        self.assertEqual(response.status_code, 200, f"Response: {response.content}")

        # Verify notify_async was called with the correct event
        mock_notify_async.assert_called_once()
        call_kwargs = mock_notify_async.call_args
        self.assertEqual(call_kwargs.kwargs.get("event"), "cache_invalidation:project")
        # Compare UUIDs since the view fetches a fresh instance from DB
        self.assertEqual(call_kwargs.kwargs.get("project").uuid, self.project.uuid)

    @mock.patch("nexus.inline_agents.api.views.notify_async")
    @mock.patch("nexus.projects.permissions._check_project_authorization")
    def test_patch_use_components_false_calls_cache_invalidation(self, mock_check_auth, mock_notify_async):
        """Test that updating use_components to False also triggers cache invalidation."""
        # Make external auth fail with RequestException to trigger internal permission fallback
        mock_check_auth.side_effect = requests.RequestException("Mocked external auth failure")

        # First set it to True
        self.project.use_components = True
        self.project.save()

        url = reverse("project-components", kwargs={"project_uuid": str(self.project.uuid)})
        response = self.client.patch(url, {"use_components": False}, format="json")

        self.assertEqual(response.status_code, 200)

        # Verify notify_async was called
        mock_notify_async.assert_called_once()
        call_kwargs = mock_notify_async.call_args
        self.assertEqual(call_kwargs.kwargs.get("event"), "cache_invalidation:project")

    @mock.patch("nexus.inline_agents.api.views.notify_async")
    @mock.patch("nexus.projects.permissions._check_project_authorization")
    def test_patch_use_components_not_called_on_missing_field(self, mock_check_auth, mock_notify_async):
        """Test that cache invalidation is NOT called when use_components field is missing."""
        # Make external auth fail with RequestException to trigger internal permission fallback
        mock_check_auth.side_effect = requests.RequestException("Mocked external auth failure")

        url = reverse("project-components", kwargs={"project_uuid": str(self.project.uuid)})
        response = self.client.patch(url, {}, format="json")

        self.assertEqual(response.status_code, 400)

        # Verify notify_async was NOT called
        mock_notify_async.assert_not_called()


class ProjectApiErrorMessageViewTestCase(TestCase):
    def setUp(self):
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = reverse("project-api-error-message", kwargs={"project_uuid": str(self.project.uuid)})
        self.cache_repo = MockCacheRepository()
        self.cache_service = CacheService(cache_repository=self.cache_repo)
        self.cache_service_patcher = mock.patch(
            "inline_agents.backends.openai.backend.CacheService",
            return_value=self.cache_service,
        )
        self.cache_service_patcher.start()

    def tearDown(self):
        self.cache_service_patcher.stop()
        self.cache_repo.clear()

    @override_settings(DEFAULT_ERROR_MESSAGES=_TEST_ERROR_MESSAGES)
    @mock.patch("inline_agents.backends.openai.backend.ConnectRESTClient")
    @mock.patch("nexus.projects.permissions._check_project_authorization")
    def test_get_returns_default_when_not_configured(self, mock_check_auth, mock_connect_cls):
        mock_check_auth.side_effect = requests.RequestException("Mocked external auth failure")
        mock_connect_cls.return_value.get_project_language.return_value = "en-us"

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"error_message": _TEST_ERROR_MESSAGES["en-us"]})

    @mock.patch("nexus.projects.permissions._check_project_authorization")
    def test_get_returns_configured_message(self, mock_check_auth):
        mock_check_auth.side_effect = requests.RequestException("Mocked external auth failure")
        self.project.api_error_message = "Unable to process your request right now."
        self.project.save(update_fields=["api_error_message"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"error_message": "Unable to process your request right now."})

    @mock.patch("nexus.projects.permissions._check_project_authorization")
    def test_patch_requires_error_message_field(self, mock_check_auth):
        mock_check_auth.side_effect = requests.RequestException("Mocked external auth failure")

        response = self.client.patch(self.url, {}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "error_message is required"})

    @mock.patch("nexus.projects.api.views.notify_async")
    @mock.patch("nexus.projects.permissions._check_project_authorization")
    def test_patch_updates_error_message(self, mock_check_auth, mock_notify_async):
        mock_check_auth.side_effect = requests.RequestException("Mocked external auth failure")

        response = self.client.patch(
            self.url,
            {"error_message": "  Custom API failure message  "},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "message": "Error message updated successfully",
                "error_message": "Custom API failure message",
            },
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.api_error_message, "Custom API failure message")
        mock_notify_async.assert_called_once()

    @override_settings(DEFAULT_ERROR_MESSAGES=_TEST_ERROR_MESSAGES)
    @mock.patch("inline_agents.backends.openai.backend.ConnectRESTClient")
    @mock.patch("nexus.projects.api.views.notify_async")
    @mock.patch("nexus.projects.permissions._check_project_authorization")
    def test_patch_clears_error_message_with_empty_string(self, mock_check_auth, mock_notify_async, mock_connect_cls):
        mock_check_auth.side_effect = requests.RequestException("Mocked external auth failure")
        mock_connect_cls.return_value.get_project_language.return_value = "en-us"
        self.project.api_error_message = "Previous message"
        self.project.save(update_fields=["api_error_message"])

        response = self.client.patch(self.url, {"error_message": "   "}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["error_message"], _TEST_ERROR_MESSAGES["en-us"])
        self.project.refresh_from_db()
        self.assertIsNone(self.project.api_error_message)


class ProjectActiveAgentsConfigViewTestCase(TestCase):
    def setUp(self):
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = reverse("active-agents-config", kwargs={"project_uuid": str(self.project.uuid)})

    def test_get_returns_empty_list_when_no_integrated_agents(self):
        response = self.client.get(self.url)
        response.render()
        content = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(content, [])

    def test_get_returns_agent_config_with_tools(self):
        from nexus.inline_agents.models import IntegratedAgent, Version
        from nexus.inline_agents.models import Agent as InlineAgent

        agent = InlineAgent.objects.create(
            name="Agente de Troca e Devolução",
            slug="troca-devolucao",
            instruction="Sempre confirme o número do pedido antes de iniciar o processo de troca",
            collaboration_instructions="Responsável por processar solicitações de troca e devolução",
            foundation_model="model:version",
            project=self.project,
        )
        Version.objects.create(
            skills=[
                {
                    "actionGroupName": "OrderLookup",
                    "description": "Busca informações de um pedido pelo número ou CPF do cliente",
                    "functionSchema": {
                        "functions": [
                            {
                                "parameters": [
                                    {
                                        "order_id": {
                                            "type": "string",
                                            "description": "Número do pedido",
                                        }
                                    },
                                    {
                                        "cpf": {
                                            "type": "string",
                                            "description": "CPF do cliente",
                                        }
                                    },
                                ]
                            }
                        ]
                    },
                }
            ],
            display_skills=[],
            agent=agent,
        )
        IntegratedAgent.objects.create(agent=agent, project=self.project, is_active=True)

        response = self.client.get(self.url)
        response.render()
        content = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(content), 1)
        row = content[0]
        self.assertEqual(row["name"], "Agente de Troca e Devolução")
        self.assertEqual(row["description"], "Responsável por processar solicitações de troca e devolução")
        self.assertEqual(
            row["instructions"],
            [{"instruction": "Sempre confirme o número do pedido antes de iniciar o processo de troca"}],
        )
        self.assertEqual(len(row["tools"]), 1)
        tool = row["tools"][0]
        self.assertEqual(tool["name"], "order-lookup")
        self.assertEqual(tool["description"], "Busca informações de um pedido pelo número ou CPF do cliente")
        self.assertEqual(len(tool["parameters"]), 2)
        param_names = {p["name"] for p in tool["parameters"]}
        self.assertEqual(param_names, {"order_id", "cpf"})

    def test_get_returns_empty_tools_when_agent_has_no_version(self):
        from nexus.inline_agents.models import IntegratedAgent
        from nexus.inline_agents.models import Agent as InlineAgent

        agent = InlineAgent.objects.create(
            name="Agent Without Version",
            slug="agent-without-version",
            instruction="Some instruction",
            collaboration_instructions="Some description",
            foundation_model="model:version",
            project=self.project,
        )
        IntegratedAgent.objects.create(agent=agent, project=self.project, is_active=True)

        response = self.client.get(self.url)
        response.render()
        content = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(content), 1)
        self.assertEqual(content[0]["tools"], [])

    def test_get_excludes_inactive_integrated_agents(self):
        from nexus.inline_agents.models import IntegratedAgent, Version
        from nexus.inline_agents.models import Agent as InlineAgent

        agent = InlineAgent.objects.create(
            name="Inactive Agent",
            slug="inactive-agent",
            instruction="Test",
            collaboration_instructions="Test",
            foundation_model="model:version",
            project=self.project,
        )
        Version.objects.create(skills=[], display_skills=[], agent=agent)
        IntegratedAgent.objects.create(agent=agent, project=self.project, is_active=False)

        response = self.client.get(self.url)
        response.render()
        content = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(content, [])

    def test_get_returns_403_without_project_access(self):
        from nexus.projects.models import ProjectAuth

        other_user = UserFactory()
        ProjectAuth.objects.filter(user=self.user, project=self.project).delete()

        client = APIClient()
        client.force_authenticate(user=other_user)
        response = client.get(self.url)

        self.assertEqual(response.status_code, 403)
