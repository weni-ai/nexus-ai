import json

from django.test import TestCase
from django.urls import reverse

from rest_framework.test import APIRequestFactory, APIClient

from nexus.usecases.projects.tests.project_factory import ProjectFactory

from nexus.agents.models import (
    Agent,
    ActiveAgent,
    Team
)

from urllib.parse import urlencode


class AgentViewsetSetTestCase(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.team = Team.objects.create(
            external_id="EXTERNALID",
            project=self.project,
        )
        self.agent = Agent.objects.create(
            external_id="AGENTID",
            slug="test_agent",
            display_name="Test Agent",
            model="model:version",
            is_official=False,
            project=self.project,
            metadata={},
            description="Test Agent Description",
            created_by=self.user,
        )
        self.agent2 = Agent.objects.create(
            external_id="AAENTID",
            slug="test_aaent",
            display_name="Information Analyst",
            model="model:version",
            is_official=False,
            project=self.project,
            metadata={},
            description="Test Agent Description",
            created_by=self.user,
        )

    def test_get_my_agents(self):
        client = APIClient()
        client.force_authenticate(user=self.user)

        url = reverse("my-agents", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        self.assertEquals(response.status_code, 200)
        self.assertEquals(len(content), 2)

    def test_get_my_agents_with_search(self):
        query_params = {"search": "information"}
        url = reverse("my-agents", kwargs={"project_uuid": str(self.project.uuid)})
        url = f"{url}?{urlencode(query_params)}"

        client = APIClient()
        client.force_authenticate(user=self.user)
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        self.assertEquals(response.status_code, 200)
        self.assertEquals(len(content), 1)
        self.assertEquals(content[0].get("name"), "Information Analyst")

    def make_agents_official(self):
        self.agent.is_official = True
        self.agent.save()
        self.agent2.is_official = True
        self.agent2.save()

    def test_get_official_agents(self):
        self.make_agents_official()

        client = APIClient()
        client.force_authenticate(user=self.user)

        url = reverse("official-agents", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        self.assertEquals(response.status_code, 200)
        self.assertEquals(len(content), 2)

    def test_get_official_agents_with_search(self):
        self.make_agents_official()
        query_params = {"search": "information"}
        url = reverse("official-agents", kwargs={"project_uuid": str(self.project.uuid)})
        url = f"{url}?{urlencode(query_params)}"

        client = APIClient()
        client.force_authenticate(user=self.user)
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        self.assertEquals(response.status_code, 200)
        self.assertEquals(len(content), 1)
        self.assertEquals(content[0].get("name"), "Information Analyst")


class TeamViewsetSetTestCase(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.team = Team.objects.create(
            external_id="EXTERNALID",
            project=self.project,
        )

    def test_get_team_empty(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("teams", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        self.assertEquals(response.status_code, 200)
        self.assertEquals(content, [])

    def test_get_team_with_agents(self):
        agent = Agent.objects.create(
            external_id="AGENTID",
            slug="test_agent",
            display_name="Test Agent",
            model="model:version",
            is_official=False,
            project=self.project,
            metadata={},
            description="Test Agent Description",
            created_by=self.user,
        )
        active_agent = ActiveAgent.objects.create(
            agent=agent,
            team=self.team,
            created_by=self.user,
        )

        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("teams", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)

        self.assertEquals(response.status_code, 200)
        self.assertEquals(len(content), 1)
        self.assertEquals(content[0].get("uuid"), str(active_agent.uuid))
        self.assertEquals(content[0].get("name"), agent.display_name)
        self.assertEquals(content[0].get("skills"), [])
        self.assertFalse(content[0].get("is_official"))
