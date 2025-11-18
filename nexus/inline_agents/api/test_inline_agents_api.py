import json
from unittest import mock

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
