import json

from django.test import TestCase
from django.urls import reverse

from rest_framework.test import APIRequestFactory, APIClient

from nexus.usecases.projects.tests.project_factory import ProjectFactory, ProjectAuthFactory
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

    def test_get_multi_agent_with_agent_builder_without_access(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        self.assertEquals(response.status_code, 200)
        self.assertEquals(content.get("multi_agents"), False)
        self.assertEquals(content.get("can_view"), False)

    def test_get_multi_agent_with_agent_builder_with_weni_access(self):
        client = APIClient()
        client.force_authenticate(user=self.user_weni)
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        self.assertEquals(response.status_code, 200)
        self.assertEquals(content.get("multi_agents"), False)
        self.assertEquals(content.get("can_view"), True)

    def test_get_multi_agent_with_agent_builder_with_vtex_access(self):
        client = APIClient()
        client.force_authenticate(user=self.user_vtex)
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        self.assertEquals(response.status_code, 200)
        self.assertEquals(content.get("multi_agents"), False)
        self.assertEquals(content.get("can_view"), True)

    def test_update_multi_agent_with_agent_builder_2_without_access(self):
        client = APIClient()
        client.force_authenticate(user=self.user_inline)
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project_2.uuid)})
        response = client.patch(url, {"multi_agents": True}, format="json")
        response.render()
        self.assertEquals(response.status_code, 403)

    def test_update_multi_agent_with_agent_builder_2_with_weni_access(self):
        client = APIClient()
        client.force_authenticate(user=self.user_weni)
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project_2.uuid)})
        response = client.patch(url, {"multi_agents": True}, format="json")
        response.render()
        content = json.loads(response.content)
        self.assertEquals(response.status_code, 200)
        self.assertEquals(content.get("multi_agents"), True)

    def test_update_multi_agent_with_agent_builder_2_with_vtex_access(self):
        client = APIClient()
        client.force_authenticate(user=self.user_vtex)
        url = reverse("multi-agents", kwargs={"project_uuid": str(self.project_2.uuid)})
        response = client.patch(url, {"multi_agents": True}, format="json")
        response.render()
        content = json.loads(response.content)
        self.assertEquals(response.status_code, 200)
        self.assertEquals(content.get("multi_agents"), True)
