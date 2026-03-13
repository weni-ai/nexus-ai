import json
from unittest import mock
from urllib.parse import urlencode

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory, TestCase
from django.urls import reverse
from rest_framework.test import APIClient, APIRequestFactory

from nexus.agents.api.views import InternalCommunicationPermission
from nexus.agents.models import Team
from nexus.inline_agents.models import Agent as InlineAgent
from nexus.inline_agents.models import AgentGroup, IntegratedAgent, Version
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.users.tests.user_factory import UserFactory


class AgentViewsetSetTestCase(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.team = Team.objects.create(
            external_id="EXTERNALID",
            project=self.project,
        )
        self.agent = InlineAgent.objects.create(
            name="Test Agent",
            slug="test-agent",
            instruction="Test Agent Description",
            collaboration_instructions="Test Agent Description",
            foundation_model="model:version",
            project=self.project,
        )
        self.agent2 = InlineAgent.objects.create(
            name="Information Analyst",
            slug="test-analyst",
            instruction="Test Agent Description",
            collaboration_instructions="Test Agent Description",
            foundation_model="model:version",
            project=self.project,
        )

    def test_get_my_agents(self):
        client = APIClient()
        client.force_authenticate(user=self.user)

        url = reverse("my-agents", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(content), 2)

    def test_get_my_agents_with_search(self):
        query_params = {"search": "information"}
        url = reverse("my-agents", kwargs={"project_uuid": str(self.project.uuid)})
        url = f"{url}?{urlencode(query_params)}"

        client = APIClient()
        client.force_authenticate(user=self.user)
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(content), 1)
        self.assertEqual(content[0].get("name"), "Information Analyst")

    def make_agents_official(self):
        self.agent.is_official = True
        self.agent.source_type = InlineAgent.PLATFORM
        self.agent.save()
        self.agent2.is_official = True
        self.agent2.source_type = InlineAgent.PLATFORM
        self.agent2.save()

    def test_get_official_agents(self):
        self.make_agents_official()

        client = APIClient()
        client.force_authenticate(user=self.user)

        url = reverse("official-agents", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(content), 2)

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
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(content), 1)
        self.assertEqual(content[0].get("name"), "Information Analyst")


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
        self.assertEqual(response.status_code, 200)
        expected = {"manager": {"external_id": ""}, "agents": []}
        self.assertEqual(content, expected)

    def test_get_team_with_agents(self):
        agent = InlineAgent.objects.create(
            name="Test Agent",
            slug="test_agent",
            instruction="Test Agent Description",
            collaboration_instructions="Test Agent Description",
            foundation_model="model:version",
            project=self.project,
        )
        # Create a version for the agent
        from nexus.inline_agents.models import Version

        Version.objects.create(
            skills=[{"name": "test_skill", "description": "test description"}],
            display_skills=[{"name": "test_skill", "description": "test description"}],
            agent=agent,
        )
        IntegratedAgent.objects.create(
            agent=agent,
            project=self.project,
        )

        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("teams", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(content["agents"]), 1)
        self.assertEqual(content["agents"][0].get("uuid"), str(agent.uuid))
        self.assertEqual(content["agents"][0].get("name"), agent.name)
        self.assertTrue(content["agents"][0].get("active", True))

    def test_get_team_excludes_inactive_integrated_agents(self):
        """Agents with is_active=False on IntegratedAgent do not appear in team list."""

        agent = InlineAgent.objects.create(
            name="Inactive Agent",
            slug="inactive_agent",
            instruction="Test",
            collaboration_instructions="Test",
            foundation_model="model:version",
            project=self.project,
        )
        Version.objects.create(
            skills=[],
            display_skills=[],
            agent=agent,
        )
        IntegratedAgent.objects.create(
            agent=agent,
            project=self.project,
            is_active=False,
        )
        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("teams", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(content["agents"]), 0)


class ActivateAgentViewTestCase(TestCase):
    def setUp(self):
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.agent = InlineAgent.objects.create(
            name="Test Agent",
            slug="test-agent",
            instruction="Test",
            collaboration_instructions="Test",
            foundation_model="model:version",
            project=self.project,
        )
        from nexus.inline_agents.models import Version

        Version.objects.create(skills=[], display_skills=[], agent=self.agent)
        IntegratedAgent.objects.create(agent=self.agent, project=self.project)

    def test_patch_activate_returns_200_and_active_true(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse(
            "activate-agent",
            kwargs={
                "project_uuid": str(self.project.uuid),
                "agent_uuid": str(self.agent.uuid),
            },
        )
        response = client.patch(url, {"active": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"active": True})
        ia = IntegratedAgent.objects.get(agent=self.agent, project=self.project)
        self.assertTrue(ia.is_active)

    def test_patch_deactivate_returns_200_and_active_false(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse(
            "activate-agent",
            kwargs={
                "project_uuid": str(self.project.uuid),
                "agent_uuid": str(self.agent.uuid),
            },
        )
        response = client.patch(url, {"active": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"active": False})
        ia = IntegratedAgent.objects.get(agent=self.agent, project=self.project)
        self.assertFalse(ia.is_active)

    def test_patch_missing_active_returns_400(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse(
            "activate-agent",
            kwargs={
                "project_uuid": str(self.project.uuid),
                "agent_uuid": str(self.agent.uuid),
            },
        )
        response = client.patch(url, {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("active", response.json().get("error", ""))

    def test_patch_invalid_active_returns_400(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse(
            "activate-agent",
            kwargs={
                "project_uuid": str(self.project.uuid),
                "agent_uuid": str(self.agent.uuid),
            },
        )
        response = client.patch(url, {"active": "true"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("active", response.json().get("error", ""))

    def test_patch_integrated_agent_not_found_returns_404(self):
        agent2 = InlineAgent.objects.create(
            name="Other Agent",
            slug="other-agent",
            instruction="Test",
            collaboration_instructions="Test",
            foundation_model="model:version",
            project=self.project,
        )
        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse(
            "activate-agent",
            kwargs={
                "project_uuid": str(self.project.uuid),
                "agent_uuid": str(agent2.uuid),
            },
        )
        response = client.patch(url, {"active": True}, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertIn("Integrated agent not found", response.json().get("error", ""))


class AssignAgentViewTestCase(TestCase):
    """Assign endpoint must reactivate existing inactive IntegratedAgent and return active state."""

    def setUp(self):
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.agent = InlineAgent.objects.create(
            name="Assign Test Agent",
            slug="assign-test-agent",
            instruction="Test",
            collaboration_instructions="Test",
            foundation_model="model:version",
            project=self.project,
        )
        Version.objects.create(skills=[], display_skills=[], agent=self.agent)

    def test_assign_reactivates_deactivated_integrated_agent_and_appears_in_team(self):
        IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            is_active=False,
        )

        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse(
            "assign-agents",
            kwargs={
                "project_uuid": str(self.project.uuid),
                "agent_uuid": str(self.agent.uuid),
            },
        )
        response = client.patch(url, {"assigned": True}, format="json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["assigned"], "assign endpoint should return assigned=True")
        self.assertTrue(data["active"], "assign endpoint should return active=True after reactivation")

        integrated_agent = IntegratedAgent.objects.get(agent=self.agent, project=self.project)
        self.assertTrue(
            integrated_agent.is_active,
            "IntegratedAgent should be active after assign when it was previously deactivated",
        )

        team_url = reverse("teams", kwargs={"project_uuid": str(self.project.uuid)})
        team_response = client.get(team_url)
        team_response.render()
        team_content = json.loads(team_response.content)
        self.assertEqual(team_response.status_code, 200)
        agent_uuids = [a["uuid"] for a in team_content.get("agents", [])]
        self.assertIn(
            str(self.agent.uuid),
            agent_uuids,
            "Reactivated agent should appear in team list (filtered by is_active=True)",
        )


class GroupUnassignmentTestCase(TestCase):
    """Regression: group unassignment must delete all IntegratedAgent rows in the group (active and inactive)."""

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_group_unassignment_deletes_active_and_inactive_integrated_agents(self, mock_has_permission):
        mock_has_permission.return_value = True

        target_project = ProjectFactory()
        user = target_project.created_by
        owner_project = ProjectFactory()

        group = AgentGroup.objects.create(name="Test Group", slug="test-group-unassign", shared_config={})

        agent1 = InlineAgent.objects.create(
            name="Group Agent 1",
            slug="group-agent-1",
            instruction="Test",
            collaboration_instructions="Test",
            foundation_model="model:version",
            project=owner_project,
            group=group,
            is_official=True,
            source_type=InlineAgent.PLATFORM,
        )
        agent2 = InlineAgent.objects.create(
            name="Group Agent 2",
            slug="group-agent-2",
            instruction="Test",
            collaboration_instructions="Test",
            foundation_model="model:version",
            project=owner_project,
            group=group,
            is_official=True,
            source_type=InlineAgent.PLATFORM,
        )
        Version.objects.create(skills=[], display_skills=[], agent=agent1)
        Version.objects.create(skills=[], display_skills=[], agent=agent2)

        ia_active = IntegratedAgent.objects.create(agent=agent1, project=target_project, is_active=True)
        ia_inactive = IntegratedAgent.objects.create(agent=agent2, project=target_project, is_active=False)

        self.assertEqual(IntegratedAgent.objects.filter(project=target_project).count(), 2)

        client = APIClient()
        client.force_authenticate(user=user)
        url = reverse("v1-official-agents")
        url = f"{url}?project_uuid={target_project.uuid}&group={group.slug}"
        response = client.post(url, {"assigned": False}, format="json", HTTP_AUTHORIZATION="Bearer test-token")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(IntegratedAgent.objects.filter(pk=ia_active.pk).exists())
        self.assertFalse(IntegratedAgent.objects.filter(pk=ia_inactive.pk).exists())
        self.assertEqual(IntegratedAgent.objects.filter(project=target_project).count(), 0)


class TestCommunicateInternallyPermission(TestCase):
    def setUp(self):
        self.user = UserFactory()
        content_type = ContentType.objects.get_for_model(self.user)
        permission, created = Permission.objects.get_or_create(
            codename="can_communicate_internally",
            name="can communicate internally",
            content_type=content_type,
        )
        self.user.user_permissions.add(permission)
        self.factory = RequestFactory()

    def test_permission_granted(self):
        request = self.factory.get("/")
        request.user = self.user
        permission = InternalCommunicationPermission()
        self.assertTrue(permission.has_permission(request, None))

    def test_permission_denied(self):
        user_without_permission = UserFactory()
        request = self.factory.get("/")
        request.user = user_without_permission
        permission = InternalCommunicationPermission()
        self.assertFalse(permission.has_permission(request, None))


class RationaleViewTestCase(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.team = Team.objects.create(external_id="EXTERNALID", project=self.project, metadata={})
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_get_rationale_default_value(self):
        url = reverse("project-rationale", kwargs={"project_uuid": str(self.project.uuid)})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"rationale": False})

    def test_get_rationale_custom_value(self):
        self.team.metadata["rationale"] = True
        self.team.save()

        url = reverse("project-rationale", kwargs={"project_uuid": str(self.project.uuid)})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"rationale": True})

    def test_patch_rationale_without_value(self):
        url = reverse("project-rationale", kwargs={"project_uuid": str(self.project.uuid)})
        response = self.client.patch(url, data={}, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "rationale is required"})

    def test_patch_rationale_success(self):
        url = reverse("project-rationale", kwargs={"project_uuid": str(self.project.uuid)})

        data = {"rationale": True}

        response = self.client.patch(url, data=json.dumps(data), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Rationale updated successfully", "rationale": True})

        # Verify the change was persisted
        self.team.refresh_from_db()
        self.assertTrue(self.team.metadata["rationale"])

    def test_patch_rationale_toggle(self):
        # Set initial value
        self.team.metadata["rationale"] = True
        self.team.save()

        url = reverse("project-rationale", kwargs={"project_uuid": str(self.project.uuid)})
        response = self.client.patch(url, data=json.dumps({"rationale": False}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Rationale updated successfully", "rationale": False})

        # Verify the change was persisted
        self.team.refresh_from_db()
        self.assertFalse(self.team.metadata["rationale"])
