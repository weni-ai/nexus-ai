from uuid import uuid4

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.inline_agents.models import Agent, IntegratedAgent
from nexus.projects.api.projects_agents_views import ProjectsAgentsView
from nexus.projects.models import Project
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.users.tests.user_factory import UserFactory


class TestProjectsAgentsView(TestCase):
    def setUp(self):
        self.project = ProjectFactory(name="Copilot A", inline_agent_switch=True)
        self.other_project = ProjectFactory(
            name="Copilot B",
            inline_agent_switch=True,
            org=self.project.org,
            created_by=self.project.created_by,
        )
        self.ab1_project = Project.objects.create(
            name="AB 1 Project",
            org=self.project.org,
            created_by=self.project.created_by,
            inline_agent_switch=False,
        )
        self.catalog_project = ProjectFactory(
            name="Official Catalog",
            inline_agent_switch=True,
            org=self.project.org,
            created_by=self.project.created_by,
        )

        self.custom_agent = Agent.objects.create(
            name="Custom",
            slug="custom-agent",
            project=self.project,
            instruction="i",
            collaboration_instructions="c",
            is_official=False,
        )
        IntegratedAgent.objects.create(agent=self.custom_agent, project=self.project, is_active=True)

        self.official_agent = Agent.objects.create(
            name="Official",
            slug="official-agent",
            project=self.catalog_project,
            instruction="i",
            collaboration_instructions="c",
            is_official=True,
        )
        IntegratedAgent.objects.create(agent=self.official_agent, project=self.project, is_active=True)

        inactive_custom = Agent.objects.create(
            name="Inactive Custom",
            slug="inactive-custom",
            project=self.project,
            instruction="i",
            collaboration_instructions="c",
            is_official=False,
        )
        IntegratedAgent.objects.create(agent=inactive_custom, project=self.project, is_active=False)

        Agent.objects.create(
            name="Unassigned Custom",
            slug="unassigned-custom",
            project=self.project,
            instruction="i",
            collaboration_instructions="c",
            is_official=False,
        )

        other_custom = Agent.objects.create(
            name="Other Custom",
            slug="other-custom",
            project=self.other_project,
            instruction="i",
            collaboration_instructions="c",
            is_official=False,
        )
        IntegratedAgent.objects.create(agent=other_custom, project=self.other_project, is_active=True)

        self.internal_user = UserFactory()
        ct = ContentType.objects.get_for_model(self.internal_user)
        perm, _ = Permission.objects.get_or_create(
            codename="can_communicate_internally",
            name="can communicate internally",
            content_type=ct,
        )
        self.internal_user.user_permissions.add(perm)
        self.internal_user = type(self.internal_user).objects.get(pk=self.internal_user.pk)

        self.factory = APIRequestFactory()
        self.view = ProjectsAgentsView.as_view()
        self.url = reverse("projects-agents-v2")

    def _get(self, params=None, user=None):
        request = self.factory.get(self.url, data=params or {})
        force_authenticate(request, user=user or self.internal_user)
        return self.view(request)

    def test_requires_internal_permission(self):
        response = self._get(user=UserFactory(), params={"project_uuids": str(self.project.uuid)})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_project_uuids_returns_400(self):
        response = self._get()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project_uuids", response.data)

    def test_invalid_project_uuid_returns_400(self):
        response = self._get({"project_uuids": "not-a-uuid"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project_uuids", response.data)

    def test_lists_active_team_agents_for_one_project(self):
        response = self._get({"project_uuids": str(self.project.uuid)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

        row = response.data["results"][0]
        self.assertEqual(row["project_uuid"], str(self.project.uuid))
        self.assertEqual(row["project_name"], "Copilot A")
        self.assertEqual(row["custom_agents_count"], 1)
        self.assertEqual(row["official_agents_count"], 1)
        self.assertEqual(
            [(agent["slug"], agent["is_official"]) for agent in row["agents"]],
            [("official-agent", True), ("custom-agent", False)],
        )
        self.assertEqual(row["agents"][0]["uuid"], str(self.official_agent.uuid))
        self.assertEqual(row["agents"][0]["name"], "Official")
        self.assertEqual(row["agents"][1]["uuid"], str(self.custom_agent.uuid))
        self.assertEqual(row["agents"][1]["name"], "Custom")

    def test_lists_multiple_projects_in_requested_order(self):
        response = self._get({"project_uuids": f"{self.other_project.uuid},{self.project.uuid}"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [row["project_uuid"] for row in response.data["results"]],
            [str(self.other_project.uuid), str(self.project.uuid)],
        )
        self.assertEqual(response.data["results"][0]["custom_agents_count"], 1)
        self.assertEqual(response.data["results"][0]["official_agents_count"], 0)
        self.assertEqual(response.data["results"][1]["custom_agents_count"], 1)
        self.assertEqual(response.data["results"][1]["official_agents_count"], 1)

    def test_omits_ab1_and_unknown_projects(self):
        response = self._get({"project_uuids": f"{self.ab1_project.uuid},{uuid4()},{self.project.uuid}"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["project_uuid"], str(self.project.uuid))

    def test_includes_eligible_project_with_no_active_agents(self):
        empty_project = ProjectFactory(
            name="Empty Copilot",
            inline_agent_switch=True,
            org=self.project.org,
            created_by=self.project.created_by,
        )
        response = self._get({"project_uuids": str(empty_project.uuid)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.data["results"][0]
        self.assertEqual(row["custom_agents_count"], 0)
        self.assertEqual(row["official_agents_count"], 0)
        self.assertEqual(row["agents"], [])
