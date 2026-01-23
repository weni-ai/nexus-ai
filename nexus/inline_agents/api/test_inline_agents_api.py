import json
from unittest import mock

import requests
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient, APIRequestFactory

from nexus.usecases.projects.tests.project_factory import ProjectAuthFactory, ProjectFactory
from nexus.usecases.users.tests.user_factory import UserFactory


class MultiAgentViewTestCase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

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
