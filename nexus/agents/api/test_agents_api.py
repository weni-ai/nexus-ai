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
from nexus.inline_agents.models import (
    MCP,
    AgentGroup,
    AgentGroupModal,
    AgentSystem,
    IntegratedAgent,
    MCPConfigOption,
    MCPCredentialTemplate,
    Version,
)
from nexus.inline_agents.models import Agent as InlineAgent
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

    def test_get_my_agents_name_is_group_not_agent_template(self):
        group = AgentGroup.objects.create(name="Returns & exchanges", slug="returns-group-test-unique")
        agent_grouped = InlineAgent.objects.create(
            name="Reversso - Returns Agent",
            slug="reversso-returns-test",
            instruction="x",
            collaboration_instructions="y",
            foundation_model="model:version",
            project=self.project,
            group=group,
        )
        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("my-agents", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        row = next(c for c in content if c.get("uuid") == str(agent_grouped.uuid))
        self.assertEqual(row["name"], "Returns & exchanges")

    def test_get_my_agents_name_prefers_modal_agent_name(self):
        group = AgentGroup.objects.create(name="Group Title", slug="modal-group-test-unique")
        AgentGroupModal.objects.create(group=group, agent_name="Product Concierge")
        agent_grouped = InlineAgent.objects.create(
            name="Product Concierge Default VTEX",
            slug="pc-modal-test",
            instruction="x",
            collaboration_instructions="y",
            foundation_model="model:version",
            project=self.project,
            group=group,
        )
        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("my-agents", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        row = next(c for c in content if c.get("uuid") == str(agent_grouped.uuid))
        self.assertEqual(row["name"], "Product Concierge")

    def test_get_my_agents_includes_mcp_definition(self):
        system = AgentSystem.objects.create(name="Test MCP System", slug="test-mcp-system-my-agents-xyz")
        mcp = MCP.objects.create(name="Test MCP", slug="test-mcp-my-agents-xyz", system=system)
        MCPConfigOption.objects.create(
            mcp=mcp,
            name="REGION_TOGGLE",
            label="Regionalization",
            type=MCPConfigOption.SWITCH,
            options=[],
            is_required=False,
            default_value=True,
        )
        MCPCredentialTemplate.objects.create(
            mcp=mcp,
            name="SYNERISE_API_TOKEN",
            label="Synerise API Key",
            placeholder="your-api-key-here",
            is_confidential=True,
        )
        agent_with_mcp = InlineAgent.objects.create(
            name="Concierge With MCP",
            slug="concierge-mcp-my-agents-xyz",
            instruction="x",
            collaboration_instructions="y",
            foundation_model="model:version",
            project=self.project,
        )
        agent_with_mcp.mcps.add(mcp)

        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("my-agents", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content)
        row = next(c for c in content if c.get("uuid") == str(agent_with_mcp.uuid))
        self.assertIn("mcp_definition", row)
        self.assertEqual(len(row["mcp_definition"]["config"]), 1)
        self.assertEqual(row["mcp_definition"]["config"][0]["name"], "REGION_TOGGLE")
        self.assertEqual(len(row["mcp_definition"]["credentials"]), 1)
        self.assertEqual(row["mcp_definition"]["credentials"][0]["name"], "SYNERISE_API_TOKEN")
        cred_names = {c["name"] for c in row["credentials"]}
        self.assertNotIn("SYNERISE_API_TOKEN", cred_names)

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

    def test_get_team_includes_about_locale_map_when_group_modal_exists(self):
        group = AgentGroup.objects.create(name="Modal Pres", slug="modal-pres-teams-unique")
        AgentGroupModal.objects.create(
            group=group,
            agent_name="Catalog",
            about_en="About EN",
            about_es="About ES",
            about_pt="About PT",
            conversation_example_en=[{"text": "Hello", "direction": "incoming"}],
            conversation_example_es=[],
            conversation_example_pt=[],
        )
        agent_grouped = InlineAgent.objects.create(
            name="Template Name",
            slug="modal-pres-agent-teams",
            instruction="x",
            collaboration_instructions="y",
            foundation_model="model:version",
            project=self.project,
            group=group,
        )
        Version.objects.create(skills=[], display_skills=[], agent=agent_grouped)
        IntegratedAgent.objects.create(agent=agent_grouped, project=self.project)

        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("teams", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        row = next(a for a in content["agents"] if a.get("uuid") == str(agent_grouped.uuid))
        about = row["about"]
        self.assertEqual(about["en"], "About EN")
        self.assertEqual(about["pt"], "About PT")
        self.assertEqual(about["es"], "About ES")
        self.assertNotIn("presentation", row)

    def test_get_team_about_null_without_group(self):
        agent = InlineAgent.objects.create(
            name="No Group Agent",
            slug="no_group_team_agent",
            instruction="Test",
            collaboration_instructions="Test",
            foundation_model="model:version",
            project=self.project,
        )
        Version.objects.create(skills=[], display_skills=[], agent=agent)
        IntegratedAgent.objects.create(agent=agent, project=self.project)

        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("teams", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        row = content["agents"][0]
        self.assertIsNone(row.get("about"))

    def test_get_team_mcp_description_locale_map(self):
        """Teams API returns MCP description as en/pt/es map (not a single collapsed string)."""
        system = AgentSystem.objects.create(name="Team MCP System", slug="team-mcp-sys-unique")
        mcp = MCP.objects.create(
            name="Team Catalog MCP",
            slug="team-catalog-mcp-unique",
            description_en="English MCP",
            description_pt="Portuguese MCP",
            description_es="Spanish MCP",
            system=system,
        )
        agent = InlineAgent.objects.create(
            name="MCP Agent",
            slug="team-mcp-agent-unique",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="model:version",
            project=self.project,
        )
        agent.mcps.add(mcp)
        Version.objects.create(skills=[], display_skills=[], agent=agent)
        IntegratedAgent.objects.create(
            agent=agent,
            project=self.project,
            metadata={
                "mcp": "Team Catalog MCP",
                "system": system.slug,
                "mcp_config": {},
            },
        )

        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("teams", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        response.render()
        content = json.loads(response.content)
        row = next(a for a in content["agents"] if a.get("uuid") == str(agent.uuid))
        mcp_payload = row["mcp_definition"]
        self.assertEqual(mcp_payload["name"], "Team Catalog MCP")
        desc = mcp_payload["description"]
        self.assertEqual(desc["en"], "English MCP")
        self.assertEqual(desc["pt"], "Portuguese MCP")
        self.assertEqual(desc["es"], "Spanish MCP")


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

    def test_assign_sets_mcp_metadata_when_agent_has_single_active_mcp(self):
        """Legacy PATCH assign infers mcp/system when the agent has exactly one active MCP."""
        system = AgentSystem.objects.create(name="Infer MCP System", slug="infer-mcp-system-unique")
        mcp = MCP.objects.create(
            name="Infer Catalog MCP",
            slug="infer-catalog-mcp-unique",
            system=system,
        )
        agent = InlineAgent.objects.create(
            name="Single MCP Assign Agent",
            slug="single-mcp-assign-agent-unique",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="model:version",
            project=self.project,
        )
        agent.mcps.add(mcp)
        Version.objects.create(skills=[], display_skills=[], agent=agent)

        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse(
            "assign-agents",
            kwargs={
                "project_uuid": str(self.project.uuid),
                "agent_uuid": str(agent.uuid),
            },
        )
        response = client.patch(url, {"assigned": True}, format="json")
        self.assertEqual(response.status_code, 200)

        integrated_agent = IntegratedAgent.objects.get(agent=agent, project=self.project)
        self.assertEqual(integrated_agent.metadata.get("mcp"), "Infer Catalog MCP")
        self.assertEqual(integrated_agent.metadata.get("system"), "infer-mcp-system-unique")

    def test_assign_does_not_set_mcp_metadata_when_multiple_active_mcps(self):
        system = AgentSystem.objects.create(name="Multi MCP System", slug="multi-mcp-system-unique")
        mcp_a = MCP.objects.create(name="MCP A", slug="multi-mcp-a-unique", system=system)
        mcp_b = MCP.objects.create(name="MCP B", slug="multi-mcp-b-unique", system=system)
        agent = InlineAgent.objects.create(
            name="Multi MCP Assign Agent",
            slug="multi-mcp-assign-agent-unique",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="model:version",
            project=self.project,
        )
        agent.mcps.add(mcp_a, mcp_b)
        Version.objects.create(skills=[], display_skills=[], agent=agent)

        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse(
            "assign-agents",
            kwargs={
                "project_uuid": str(self.project.uuid),
                "agent_uuid": str(agent.uuid),
            },
        )
        response = client.patch(url, {"assigned": True}, format="json")
        self.assertEqual(response.status_code, 200)

        integrated_agent = IntegratedAgent.objects.get(agent=agent, project=self.project)
        self.assertIsNone(integrated_agent.metadata.get("mcp"))
        self.assertIsNone(integrated_agent.metadata.get("system"))


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


class OfficialAgentsV1NameFilterTestCase(TestCase):
    """GET /api/v1/official/agents `name` matches group title for grouped agents and Agent.name for legacy."""

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_grouped_matches_group_name_not_template_agent_name(self, mock_has_permission):
        mock_has_permission.return_value = True

        target_project = ProjectFactory()
        user = target_project.created_by
        owner_project = ProjectFactory()

        group = AgentGroup.objects.create(
            name="Feedback Recorder", slug="official-name-filter-group-unique", shared_config={}
        )
        agent = InlineAgent.objects.create(
            name="NPS Recorder 2.0",
            slug="official-name-filter-agent-unique",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="m",
            project=owner_project,
            group=group,
            is_official=True,
            source_type=InlineAgent.PLATFORM,
        )
        Version.objects.create(skills=[], display_skills=[], agent=agent)

        client = APIClient()
        client.force_authenticate(user=user)
        list_url = reverse("v1-official-agents")

        ok = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "name": "feed"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(ok.status_code, 200)
        groups = [a["group"] for a in ok.json()["new"]["agents"]]
        self.assertIn(group.slug, groups)

        no_match = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "name": "nps"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(no_match.status_code, 200)
        self.assertEqual(no_match.json()["new"]["agents"], [])

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_grouped_matches_modal_agent_name_when_set(self, mock_has_permission):
        mock_has_permission.return_value = True

        target_project = ProjectFactory()
        user = target_project.created_by
        owner_project = ProjectFactory()

        group = AgentGroup.objects.create(
            name="Internal", slug="official-name-filter-modal-group-unique", shared_config={}
        )
        AgentGroupModal.objects.create(group=group, agent_name="Catalog Shop")
        agent = InlineAgent.objects.create(
            name="Template VTEX Only",
            slug="official-name-filter-modal-agent-unique",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="m",
            project=owner_project,
            group=group,
            is_official=True,
            source_type=InlineAgent.PLATFORM,
        )
        Version.objects.create(skills=[], display_skills=[], agent=agent)

        client = APIClient()
        client.force_authenticate(user=user)
        list_url = reverse("v1-official-agents")
        resp = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "name": "catalog"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(resp.status_code, 200)
        groups = [a["group"] for a in resp.json()["new"]["agents"]]
        self.assertIn(group.slug, groups)

        miss_internal = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "name": "internal"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(miss_internal.status_code, 200)
        self.assertNotIn(group.slug, [a["group"] for a in miss_internal.json()["new"]["agents"]])

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_grouped_modal_title_does_not_fall_back_to_group_name(self, mock_has_permission):
        """When modal agent_name is set, `name` must not match only AgentGroup.name (UI shows modal)."""
        mock_has_permission.return_value = True

        target_project = ProjectFactory()
        user = target_project.created_by
        owner_project = ProjectFactory()

        group = AgentGroup.objects.create(name="order_payment", slug="official-name-modal-only-group", shared_config={})
        AgentGroupModal.objects.create(group=group, agent_name="Payment Agent")
        agent = InlineAgent.objects.create(
            name="Payment Agent (VTEX)",
            slug="official-name-modal-only-agent",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="m",
            project=owner_project,
            group=group,
            is_official=True,
            source_type=InlineAgent.PLATFORM,
        )
        Version.objects.create(skills=[], display_skills=[], agent=agent)

        client = APIClient()
        client.force_authenticate(user=user)
        list_url = reverse("v1-official-agents")

        no_order = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "name": "order"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(no_order.status_code, 200)
        self.assertNotIn(group.slug, [a["group"] for a in no_order.json()["new"]["agents"]])

        yes_pay = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "name": "pay"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(yes_pay.status_code, 200)
        self.assertIn(group.slug, [a["group"] for a in yes_pay.json()["new"]["agents"]])

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_legacy_without_group_matches_agent_name(self, mock_has_permission):
        mock_has_permission.return_value = True

        target_project = ProjectFactory()
        user = target_project.created_by
        owner_project = ProjectFactory()

        legacy = InlineAgent.objects.create(
            name="Standalone Recorder",
            slug="official-name-filter-legacy-unique",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="m",
            project=owner_project,
            group=None,
            is_official=True,
            source_type=InlineAgent.PLATFORM,
        )
        Version.objects.create(skills=[], display_skills=[], agent=legacy)

        client = APIClient()
        client.force_authenticate(user=user)
        list_url = reverse("v1-official-agents")

        hit = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "name": "standalone"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(hit.status_code, 200)
        legacy_uuids = [a["uuid"] for a in hit.json()["legacy"]]
        self.assertIn(str(legacy.uuid), legacy_uuids)

        miss = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "name": "no_such_substring_xyz"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(miss.status_code, 200)
        self.assertEqual(miss.json()["legacy"], [])

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_name_prefix_does_not_match_mid_word_substring(self, mock_has_permission):
        mock_has_permission.return_value = True

        target_project = ProjectFactory()
        user = target_project.created_by
        owner_project = ProjectFactory()

        group = AgentGroup.objects.create(
            name="Feedback Recorder", slug="official-name-prefix-midword-group", shared_config={}
        )
        agent = InlineAgent.objects.create(
            name="NPS Recorder 2.0",
            slug="official-name-prefix-midword-agent",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="m",
            project=owner_project,
            group=group,
            is_official=True,
            source_type=InlineAgent.PLATFORM,
        )
        Version.objects.create(skills=[], display_skills=[], agent=agent)

        client = APIClient()
        client.force_authenticate(user=user)
        list_url = reverse("v1-official-agents")
        resp = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "name": "order"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(group.slug, [a["group"] for a in resp.json()["new"]["agents"]])

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_name_prefix_matches_start_of_second_word(self, mock_has_permission):
        mock_has_permission.return_value = True

        target_project = ProjectFactory()
        user = target_project.created_by
        owner_project = ProjectFactory()

        legacy = InlineAgent.objects.create(
            name="VTEX Order Helper",
            slug="official-name-prefix-second-word",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="m",
            project=owner_project,
            group=None,
            is_official=True,
            source_type=InlineAgent.PLATFORM,
        )
        Version.objects.create(skills=[], display_skills=[], agent=legacy)

        client = APIClient()
        client.force_authenticate(user=user)
        list_url = reverse("v1-official-agents")
        resp = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "name": "order"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(str(legacy.uuid), [a["uuid"] for a in resp.json()["legacy"]])

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_name_prefix_backend_not_feedback_recorder(self, mock_has_permission):
        mock_has_permission.return_value = True

        target_project = ProjectFactory()
        user = target_project.created_by
        owner_project = ProjectFactory()

        fb_group = AgentGroup.objects.create(
            name="Feedback Recorder", slug="official-name-prefix-fb-group", shared_config={}
        )
        fb_agent = InlineAgent.objects.create(
            name="NPS Recorder 2.0",
            slug="official-name-prefix-fb-agent",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="m",
            project=owner_project,
            group=fb_group,
            is_official=True,
            source_type=InlineAgent.PLATFORM,
        )
        Version.objects.create(skills=[], display_skills=[], agent=fb_agent)

        be_legacy = InlineAgent.objects.create(
            name="Backend Agent",
            slug="official-name-prefix-backend-agent",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="m",
            project=owner_project,
            group=None,
            is_official=True,
            source_type=InlineAgent.PLATFORM,
        )
        Version.objects.create(skills=[], display_skills=[], agent=be_legacy)

        client = APIClient()
        client.force_authenticate(user=user)
        list_url = reverse("v1-official-agents")
        resp = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "name": "back"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(fb_group.slug, [a["group"] for a in resp.json()["new"]["agents"]])
        self.assertIn(str(be_legacy.uuid), [a["uuid"] for a in resp.json()["legacy"]])


class OfficialAgentsV1I18nPresentationTestCase(TestCase):
    """Official list/detail APIs expose presentation and MCP description as nested locale maps (en/pt/es)."""

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_list_and_detail_include_locale_fields(self, mock_has_permission):
        mock_has_permission.return_value = True

        target_project = ProjectFactory()
        user = target_project.created_by
        owner_project = ProjectFactory()

        group = AgentGroup.objects.create(name="I18n Group", slug="i18n-group-official-test", shared_config={})
        AgentGroupModal.objects.create(
            group=group,
            agent_name="Catalog",
            about_en="About EN",
            about_es="About ES",
            about_pt="About PT",
            conversation_example_en=[{"text": "EN", "direction": "incoming"}],
            conversation_example_es=[{"text": "ES", "direction": "incoming"}],
            conversation_example_pt=[{"text": "PT", "direction": "incoming"}],
        )
        system = AgentSystem.objects.create(name="VTEX I18n Test", slug="vtex-i18n-official-test")
        mcp = MCP.objects.create(
            name="Test MCP",
            slug="test-mcp-i18n-official",
            description_en="Desc EN",
            description_es="Desc ES",
            description_pt="Desc PT",
            system=system,
        )
        group.mcps.add(mcp)
        MCPConfigOption.objects.create(
            mcp=mcp,
            name="REQ_FIELD",
            label="Required field",
            type=MCPConfigOption.TEXT,
            is_required=True,
            order=0,
        )
        MCPConfigOption.objects.create(
            mcp=mcp,
            name="OPT_FIELD",
            label="Optional field",
            type=MCPConfigOption.TEXT,
            is_required=False,
            order=1,
        )

        agent = InlineAgent.objects.create(
            name="Agent",
            slug="i18n-agent-official-test",
            instruction="i",
            collaboration_instructions="collab",
            foundation_model="m",
            project=owner_project,
            group=group,
            is_official=True,
            source_type=InlineAgent.PLATFORM,
        )
        Version.objects.create(skills=[], display_skills=[], agent=agent)

        client = APIClient()
        client.force_authenticate(user=user)
        list_url = reverse("v1-official-agents")
        list_resp = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid)},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(list_resp.status_code, 200)
        listed = list_resp.json()["new"]["agents"]
        entry = next(a for a in listed if a.get("group") == group.slug)
        pres = entry["presentation"]
        self.assertEqual(pres["about"]["en"], "About EN")
        self.assertEqual(pres["about"]["es"], "About ES")
        self.assertEqual(pres["about"]["pt"], "About PT")
        self.assertEqual(pres["conversation_example"]["en"][0]["text"], "EN")
        self.assertEqual(pres["conversation_example"]["es"][0]["text"], "ES")
        self.assertEqual(pres["conversation_example"]["pt"][0]["text"], "PT")

        detail_url = reverse("v1-official-agent-detail", kwargs={"identifier": group.slug})
        detail_resp = client.get(
            detail_url,
            {"project_uuid": str(target_project.uuid)},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(detail_resp.status_code, 200)
        body = detail_resp.json()
        dp = body["presentation"]
        self.assertEqual(dp["about"]["en"], "About EN")
        self.assertEqual(dp["about"]["pt"], "About PT")
        self.assertEqual(dp["conversation_example"]["es"][0]["text"], "ES")

        mcps_flat = body.get("MCPs") or []
        self.assertTrue(mcps_flat, "expected MCPs in detail response")
        mcp_payload = next(m for m in mcps_flat if m["name"] == "Test MCP")
        desc = mcp_payload["description"]
        self.assertEqual(desc["en"], "Desc EN")
        self.assertEqual(desc["es"], "Desc ES")
        self.assertEqual(desc["pt"], "Desc PT")
        cfg_by_name = {c["name"]: c for c in mcp_payload["config"]}
        self.assertTrue(cfg_by_name["REQ_FIELD"]["is_required"])
        self.assertFalse(cfg_by_name["OPT_FIELD"]["is_required"])


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
