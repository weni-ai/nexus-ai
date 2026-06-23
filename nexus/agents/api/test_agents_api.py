import json
from datetime import timedelta
from unittest import mock
from urllib.parse import urlencode

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Max
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory

from nexus.agents.api.views import InternalCommunicationPermission
from nexus.agents.models import Team
from nexus.inline_agents.models import (
    MCP,
    AgentCredential,
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


def _official_v1_grouped_rows(payload):
    """Official v1 list: paginated ``results`` (one row per agent group)."""
    return payload.get("results", [])


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
        for row in content:
            self.assertIn("last_updated", row)
            self.assertIsNone(row["last_updated"])

    def test_get_my_agents_last_updated_from_latest_cli_version(self):
        from nexus.inline_agents.api.serializers.catalog import format_agent_last_updated

        older = timezone.now() - timedelta(days=2)
        newer = timezone.now() - timedelta(hours=1)
        v1 = Version.objects.create(skills=[], display_skills=[], agent=self.agent)
        v2 = Version.objects.create(skills=[], display_skills=[], agent=self.agent)
        Version.objects.filter(pk=v1.pk).update(created_on=older)
        Version.objects.filter(pk=v2.pk).update(created_on=newer)
        expected = format_agent_last_updated(
            Version.objects.filter(agent=self.agent).aggregate(last=Max("created_on"))["last"]
        )

        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("my-agents", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        row = next(r for r in content if r["uuid"] == str(self.agent.uuid))
        self.assertEqual(row["last_updated"], expected)

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

    def test_get_my_agents_returns_about_locale_map_from_modal(self):
        group = AgentGroup.objects.create(name="About Group", slug="about-group-my-agents-unique")
        AgentGroupModal.objects.create(
            group=group,
            agent_name="Catalog Agent",
            about_en="About EN",
            about_pt="About PT",
            about_es="About ES",
        )
        agent_grouped = InlineAgent.objects.create(
            name="Template",
            slug="about-modal-my-agents",
            instruction="x",
            collaboration_instructions="fallback should not win",
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
        self.assertEqual(row["about"]["en"], "About EN")
        self.assertEqual(row["about"]["pt"], "About PT")
        self.assertEqual(row["about"]["es"], "About ES")
        self.assertNotIn("description", row)

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
        self.assertIn("about", row)
        self.assertNotIn("description", row)
        self.assertEqual(len(row["mcps"]), 1)
        mcp_payload = row["mcps"][0]
        self.assertEqual(len(mcp_payload["config"]), 1)
        self.assertEqual(mcp_payload["config"][0]["name"], "REGION_TOGGLE")
        self.assertEqual(len(mcp_payload["credentials"]), 1)
        self.assertEqual(mcp_payload["credentials"][0]["name"], "SYNERISE_API_TOKEN")

    def test_get_my_agents_includes_agent_credentials_in_mcps_without_linked_mcp(self):
        agent_with_credentials = InlineAgent.objects.create(
            name="VTEX Orders Agent",
            slug="vtex-orders-cred-test-xyz",
            instruction="x",
            collaboration_instructions="Consulta pedidos VTEX",
            foundation_model="model:version",
            project=self.project,
        )
        for key, label, is_confidential in (
            ("vtex_app_key", "VTEX App Key", True),
            ("vtex_account", "Conta VTEX", False),
        ):
            credential = AgentCredential.objects.create(
                project=self.project,
                key=key,
                label=label,
                placeholder=f"placeholder-{key}",
                is_confidential=is_confidential,
            )
            credential.agents.add(agent_with_credentials)

        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("my-agents", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content)
        row = next(c for c in content if c.get("uuid") == str(agent_with_credentials.uuid))
        self.assertEqual(len(row["mcps"]), 1)
        mcp_payload = row["mcps"][0]
        self.assertIsNone(mcp_payload["name"])
        self.assertEqual(mcp_payload["system"], None)
        self.assertEqual(mcp_payload["config"], [])
        cred_names = {c["name"] for c in mcp_payload["credentials"]}
        self.assertEqual(cred_names, {"vtex_app_key", "vtex_account"})
        by_name = {c["name"]: c for c in mcp_payload["credentials"]}
        self.assertEqual(by_name["vtex_app_key"]["label"], "VTEX App Key")
        self.assertTrue(by_name["vtex_app_key"]["is_confidential"])

    def test_get_my_agents_merges_agent_credentials_when_mcp_templates_empty(self):
        system = AgentSystem.objects.create(name="VTEX System", slug="vtex-system-cred-merge-xyz")
        mcp = MCP.objects.create(name="VTEX MCP", slug="vtex-mcp-cred-merge-xyz", system=system)
        agent = InlineAgent.objects.create(
            name="Agent MCP merge",
            slug="agent-mcp-cred-merge-xyz",
            instruction="x",
            collaboration_instructions="y",
            foundation_model="model:version",
            project=self.project,
        )
        agent.mcps.add(mcp)
        credential = AgentCredential.objects.create(
            project=self.project,
            key="vtex_app_token",
            label="VTEX App Token",
            placeholder="token",
            is_confidential=True,
        )
        credential.agents.add(agent)

        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("my-agents", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        row = next(c for c in content if c.get("uuid") == str(agent.uuid))
        self.assertEqual(len(row["mcps"]), 1)
        cred_names = {c["name"] for c in row["mcps"][0]["credentials"]}
        self.assertEqual(cred_names, {"vtex_app_token"})


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
        row = content["agents"][0]
        self.assertEqual(row.get("uuid"), str(agent.uuid))
        self.assertEqual(row.get("slug"), agent.slug)
        self.assertEqual(row.get("name"), agent.name)
        self.assertTrue(row.get("active", True))
        self.assertNotIn("id", row)
        self.assertNotIn("skills", row)
        self.assertNotIn("description", row)
        self.assertNotIn("mcp", row)
        self.assertIsNone(row["mcps"])
        self.assertEqual(
            row["about"],
            {"en": "Test Agent Description", "pt": None, "es": None},
        )
        self.assertIsNone(row.get("group"))

    def test_get_team_last_updated_from_latest_cli_version(self):
        from nexus.inline_agents.api.serializers.catalog import format_agent_last_updated

        agent = InlineAgent.objects.create(
            name="Versioned Agent",
            slug="versioned_agent",
            instruction="Test",
            collaboration_instructions="Test",
            foundation_model="model:version",
            project=self.project,
        )
        IntegratedAgent.objects.create(agent=agent, project=self.project)
        older = timezone.now() - timedelta(days=2)
        newer = timezone.now() - timedelta(hours=1)
        v1 = Version.objects.create(skills=[], display_skills=[], agent=agent)
        v2 = Version.objects.create(skills=[], display_skills=[], agent=agent)
        Version.objects.filter(pk=v1.pk).update(created_on=older)
        Version.objects.filter(pk=v2.pk).update(created_on=newer)
        expected = format_agent_last_updated(
            Version.objects.filter(agent=agent).aggregate(last=Max("created_on"))["last"]
        )

        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("teams", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        row = next(r for r in json.loads(response.content)["agents"] if r["uuid"] == str(agent.uuid))
        self.assertEqual(row["last_updated"], expected)

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
        self.assertEqual(row["name"], "Catalog")
        about = row["about"]
        self.assertEqual(about["en"], "About EN")
        self.assertEqual(about["pt"], "About PT")
        self.assertEqual(about["es"], "About ES")
        self.assertNotIn("presentation", row)
        self.assertIsNone(row["mcps"])
        self.assertEqual(row.get("group"), group.slug)

    def test_get_team_about_from_collaboration_instructions_without_group(self):
        agent = InlineAgent.objects.create(
            name="No Group Agent",
            slug="no_group_team_agent",
            instruction="Test",
            collaboration_instructions="Custom agent about text",
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
        self.assertEqual(
            row["about"],
            {"en": "Custom agent about text", "pt": None, "es": None},
        )

    def test_get_team_mcp_description_locale_map(self):
        """Team rows expose only the configured MCP inside ``mcps`` (one-element array)."""
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
        self.assertEqual(len(row["mcps"]), 1)
        mcp_payload = row["mcps"][0]
        self.assertEqual(mcp_payload["name"], "Team Catalog MCP")
        self.assertIsNone(mcp_payload["config"])
        self.assertEqual(mcp_payload["system"], system.name)
        desc = mcp_payload["description"]
        self.assertEqual(desc["en"], "English MCP")
        self.assertEqual(desc["pt"], "Portuguese MCP")
        self.assertEqual(desc["es"], "Spanish MCP")

    def test_get_team_mcps_from_mcp_config_only_metadata(self):
        """Expose configured constants when metadata has mcp_config but no explicit mcp key yet."""
        system = AgentSystem.objects.create(name="Team Config System", slug="team-config-sys-unique")
        mcp = MCP.objects.create(
            name="Team Config MCP",
            slug="team-config-mcp-unique",
            system=system,
        )
        MCPConfigOption.objects.create(
            mcp=mcp,
            name="country",
            label="Country",
            type=MCPConfigOption.TEXT,
        )
        agent = InlineAgent.objects.create(
            name="Config Only Agent",
            slug="team-config-only-agent",
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
            metadata={"mcp_config": {"country": "BRA"}},
        )

        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse("teams", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        response.render()
        content = json.loads(response.content)
        row = next(a for a in content["agents"] if a.get("uuid") == str(agent.uuid))
        self.assertEqual(len(row["mcps"]), 1)
        self.assertEqual(row["mcps"][0]["name"], "Team Config MCP")
        self.assertEqual(row["mcps"][0]["config"], {"Country": "BRA"})

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission", return_value=False)
    def test_get_team_internal_communication_permission_grants_access(self, _mock_has_project_perm):
        internal_user = UserFactory()
        content_type = ContentType.objects.get_for_model(internal_user)
        permission, _ = Permission.objects.get_or_create(
            codename="can_communicate_internally",
            name="can communicate internally",
            content_type=content_type,
        )
        internal_user.user_permissions.add(permission)
        internal_user = type(internal_user).objects.get(pk=internal_user.pk)

        client = APIClient()
        client.force_authenticate(user=internal_user)
        url = reverse("teams", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        self.assertEqual(response.status_code, 200)

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission", return_value=False)
    def test_get_team_unauthorized_user_returns_403(self, _mock_has_project_perm):
        unauthorized_user = UserFactory()
        client = APIClient()
        client.force_authenticate(user=unauthorized_user)
        url = reverse("teams", kwargs={"project_uuid": str(self.project.uuid)})
        response = client.get(url)
        self.assertEqual(response.status_code, 403)


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


class OfficialAgentsV1AssignCredentialsTestCase(TestCase):
    """POST /api/v1/official/agents assign + credentials (replaces removed project assign route)."""

    def setUp(self):
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.system = AgentSystem.objects.create(name="Cred System", slug="assign-cred-system-unique")
        self.mcp = MCP.objects.create(
            name="Assign Cred MCP",
            slug="assign-cred-mcp-unique",
            system=self.system,
        )
        MCPCredentialTemplate.objects.create(
            mcp=self.mcp,
            name="api_token",
            label="API token",
            placeholder="Token",
            is_confidential=True,
        )
        self.agent = InlineAgent.objects.create(
            name="Cred Assign Agent",
            slug="assign-cred-agent-unique",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="model:version",
            project=self.project,
        )
        self.agent.systems.add(self.system)
        self.agent.mcps.add(self.mcp)
        Version.objects.create(skills=[], display_skills=[], agent=self.agent)

    def _post_v1_assign(self, client, project_uuid, agent_uuid, body, *, auth_header=True):
        url = reverse("v1-official-agents")
        url = f"{url}?project_uuid={project_uuid}&agent_uuid={agent_uuid}"
        kwargs = {"format": "json"}
        if auth_header:
            kwargs["HTTP_AUTHORIZATION"] = "Bearer test-token"
        return client.post(url, body, **kwargs)

    def _post_v1_assign_group(self, client, project_uuid, group_slug, body, *, auth_header=True):
        url = reverse("v1-official-agents")
        url = f"{url}?project_uuid={project_uuid}&group={group_slug}"
        kwargs = {"format": "json"}
        if auth_header:
            kwargs["HTTP_AUTHORIZATION"] = "Bearer test-token"
        return client.post(url, body, **kwargs)

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_post_assign_accepts_blank_system_for_group_mcp_without_agent_system(self, mock_has_permission):
        mock_has_permission.return_value = True
        owner = ProjectFactory()
        group = AgentGroup.objects.create(
            name="Feedback",
            slug="feedback-blank-system-assign",
            shared_config={},
        )
        mcp = MCP.objects.create(
            name="CSAT (Customer Satisfaction Score)",
            slug="csat-blank-system-mcp-unique",
            system=None,
        )
        group.mcps.add(mcp)
        official_agent = InlineAgent.objects.create(
            name="Feedback Agent",
            slug="feedback-blank-system-agent",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="model:version",
            project=owner,
            group=group,
            is_official=True,
            source_type=InlineAgent.PLATFORM,
        )
        official_agent.mcps.add(mcp)
        Version.objects.create(skills=[], display_skills=[], agent=official_agent)

        client = APIClient()
        client.force_authenticate(user=self.user)
        response = self._post_v1_assign_group(
            client,
            str(self.project.uuid),
            group.slug,
            {
                "assigned": True,
                "system": "",
                "mcp": mcp.name,
                "mcp_config": {},
                "credentials": [],
            },
        )
        self.assertEqual(response.status_code, 200, response.json())
        self.assertTrue(response.json()["assigned"])
        integrated = IntegratedAgent.objects.get(agent=official_agent, project=self.project)
        self.assertEqual(integrated.metadata.get("mcp"), mcp.name)
        self.assertNotIn("system", integrated.metadata)

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_post_invalid_project_uuid_returns_400(self, mock_has_permission):
        mock_has_permission.return_value = True
        client = APIClient()
        client.force_authenticate(user=self.user)
        response = self._post_v1_assign(
            client,
            "not-a-uuid",
            str(self.agent.uuid),
            {"assigned": True},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("project_uuid", str(response.json()).lower())

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_post_assigned_false_unassigns(self, mock_has_permission):
        mock_has_permission.return_value = True
        IntegratedAgent.objects.create(agent=self.agent, project=self.project, is_active=True)
        client = APIClient()
        client.force_authenticate(user=self.user)
        response = self._post_v1_assign(
            client,
            str(self.project.uuid),
            str(self.agent.uuid),
            {"assigned": False},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["assigned"])
        self.assertFalse(IntegratedAgent.objects.filter(agent=self.agent, project=self.project).exists())

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_post_credentials_not_a_list_returns_400(self, mock_has_permission):
        mock_has_permission.return_value = True
        client = APIClient()
        client.force_authenticate(user=self.user)
        response = self._post_v1_assign(
            client,
            str(self.project.uuid),
            str(self.agent.uuid),
            {
                "assigned": True,
                "credentials": "not-a-list",
                "system": self.system.slug,
                "mcp": self.mcp.name,
            },
        )
        self.assertEqual(response.status_code, 400)

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_post_assign_with_credentials_creates_project_credentials(self, mock_has_permission):
        mock_has_permission.return_value = True
        client = APIClient()
        client.force_authenticate(user=self.user)
        body = {
            "assigned": True,
            "system": self.system.slug,
            "mcp": self.mcp.name,
            "credentials": [
                {
                    "name": "api_token",
                    "label": "API token",
                    "placeholder": "Token",
                    "is_confidential": True,
                    "value": "secret-value",
                }
            ],
        }
        response = self._post_v1_assign(client, str(self.project.uuid), str(self.agent.uuid), body)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["assigned"])
        self.assertIn("api_token", data.get("created_credentials", []))

        integrated = IntegratedAgent.objects.get(agent=self.agent, project=self.project)
        self.assertEqual(integrated.metadata.get("mcp"), self.mcp.name)
        self.assertEqual(integrated.metadata.get("system"), self.system.slug)

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_post_custom_agent_assign_persists_mcp_config_without_explicit_mcp(self, mock_has_permission):
        """Custom agents with one MCP can assign constants via mcp_config only."""
        mock_has_permission.return_value = True
        system = AgentSystem.objects.create(name="VTEX Custom", slug="vtex-custom-mcp-config-test")
        mcp = MCP.objects.create(
            name="Product Concierge MCP",
            slug="product-concierge-mcp-config-test",
            system=system,
        )
        MCPConfigOption.objects.create(
            mcp=mcp,
            name="country",
            label="Country",
            type=MCPConfigOption.TEXT,
        )
        custom_agent = InlineAgent.objects.create(
            name="Product Concierge Constants",
            slug="product_concierge_constants_test",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="model:version",
            project=self.project,
            is_official=False,
        )
        custom_agent.mcps.add(mcp)
        Version.objects.create(skills=[], display_skills=[], agent=custom_agent)

        client = APIClient()
        client.force_authenticate(user=self.user)
        response = self._post_v1_assign(
            client,
            str(self.project.uuid),
            str(custom_agent.uuid),
            {
                "assigned": True,
                "mcp_config": {"country": "BRA", "trade_policy": "1"},
            },
        )
        self.assertEqual(response.status_code, 200, response.json())
        integrated = IntegratedAgent.objects.get(agent=custom_agent, project=self.project)
        self.assertEqual(integrated.metadata.get("mcp"), mcp.name)
        self.assertEqual(integrated.metadata.get("system"), system.slug)
        self.assertEqual(
            integrated.metadata.get("mcp_config"),
            {"country": "BRA", "trade_policy": "1"},
        )

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_v1_official_list_group_includes_credentials_templates(self, mock_has_permission):
        mock_has_permission.return_value = True
        owner = ProjectFactory()
        group = AgentGroup.objects.create(name="Cred Group", slug="assign-cred-group-unique", shared_config={})
        official_agent = InlineAgent.objects.create(
            name="Official Cred Agent",
            slug="official-cred-agent-unique",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="m",
            project=owner,
            group=group,
            is_official=True,
            source_type=InlineAgent.PLATFORM,
        )
        official_agent.systems.add(self.system)
        official_agent.mcps.add(self.mcp)
        group.mcps.add(self.mcp)
        Version.objects.create(skills=[], display_skills=[], agent=official_agent)

        client = APIClient()
        client.force_authenticate(user=self.user)
        list_url = reverse("v1-official-agents")
        resp = client.get(
            list_url,
            {"group": group.slug},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(resp.status_code, 200)
        groups = resp.json().get("new", {}).get("agents", [])
        row = next(g for g in groups if g.get("group") == group.slug)
        creds = row.get("credentials") or []
        self.assertEqual(len(creds), 1)
        self.assertEqual(creds[0]["name"], "api_token")


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


class OfficialAgentsV1PaginationTestCase(TestCase):
    """Pagination validation for GET /api/v1/official/agents."""

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_page_size_over_max_returns_400(self, mock_has_permission):
        mock_has_permission.return_value = True
        target_project = ProjectFactory()
        user = target_project.created_by
        client = APIClient()
        client.force_authenticate(user=user)
        list_url = reverse("v1-official-agents")
        resp = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "page": "1", "page_size": "21"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(resp.status_code, 400)

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_page_below_one_returns_400(self, mock_has_permission):
        mock_has_permission.return_value = True
        target_project = ProjectFactory()
        user = target_project.created_by
        client = APIClient()
        client.force_authenticate(user=user)
        list_url = reverse("v1-official-agents")
        resp = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "page": "0", "page_size": "10"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(resp.status_code, 400)


class OfficialAgentsV1NameFilterTestCase(TestCase):
    """GET /api/v1/official/agents `name` matches modal catalog title or AgentGroup.name."""

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
        groups = [a["group"] for a in _official_v1_grouped_rows(ok.json())]
        self.assertIn(group.slug, groups)

        no_match = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "name": "nps"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(no_match.status_code, 200)
        self.assertEqual(_official_v1_grouped_rows(no_match.json()), [])

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
        groups = [a["group"] for a in _official_v1_grouped_rows(resp.json())]
        self.assertIn(group.slug, groups)

        miss_internal = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "name": "internal"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(miss_internal.status_code, 200)
        self.assertNotIn(group.slug, [a["group"] for a in _official_v1_grouped_rows(miss_internal.json())])

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
        self.assertNotIn(group.slug, [a["group"] for a in _official_v1_grouped_rows(no_order.json())])

        yes_pay = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "name": "pay"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(yes_pay.status_code, 200)
        self.assertIn(group.slug, [a["group"] for a in _official_v1_grouped_rows(yes_pay.json())])

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
        self.assertNotIn(group.slug, [a["group"] for a in _official_v1_grouped_rows(resp.json())])

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_name_prefix_matches_start_of_second_word(self, mock_has_permission):
        mock_has_permission.return_value = True

        target_project = ProjectFactory()
        user = target_project.created_by
        owner_project = ProjectFactory()

        group = AgentGroup.objects.create(
            name="VTEX Order Helper", slug="official-name-prefix-second-word-group", shared_config={}
        )
        agent = InlineAgent.objects.create(
            name="Template Agent",
            slug="official-name-prefix-second-word-agent",
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
        self.assertIn(group.slug, [a["group"] for a in _official_v1_grouped_rows(resp.json())])

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

        backend_group = AgentGroup.objects.create(
            name="Backend Agent", slug="official-name-prefix-backend-group", shared_config={}
        )
        backend_agent = InlineAgent.objects.create(
            name="Backend Catalog Agent",
            slug="official-name-prefix-backend-catalog-agent",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="m",
            project=owner_project,
            group=backend_group,
            is_official=True,
            source_type=InlineAgent.PLATFORM,
        )
        Version.objects.create(skills=[], display_skills=[], agent=backend_agent)

        client = APIClient()
        client.force_authenticate(user=user)
        list_url = reverse("v1-official-agents")
        resp = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid), "name": "back"},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(fb_group.slug, [a["group"] for a in _official_v1_grouped_rows(resp.json())])
        self.assertIn(backend_group.slug, [a["group"] for a in _official_v1_grouped_rows(resp.json())])


class OfficialAgentsV1I18nPresentationTestCase(TestCase):
    """Official v1 list exposes ``about``, ``conversation_example``, and MCP locale maps (en/pt/es)."""

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_list_includes_locale_fields(self, mock_has_permission):
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
        self.assertNotIn("available_systems", list_resp.json()["new"])
        listed = _official_v1_grouped_rows(list_resp.json())
        entry = next(a for a in listed if a.get("group") == group.slug)
        about = entry["about"]
        self.assertEqual(about["en"], "About EN")
        self.assertEqual(about["es"], "About ES")
        self.assertEqual(about["pt"], "About PT")
        cex = entry["conversation_example"]
        self.assertEqual(cex["en"][0]["text"], "EN")
        self.assertEqual(cex["es"][0]["text"], "ES")
        self.assertEqual(cex["pt"][0]["text"], "PT")

        mcps_flat = entry.get("mcps") or []
        self.assertTrue(mcps_flat, "expected MCPs in list row")
        mcp_payload = next(m for m in mcps_flat if m["name"] == "Test MCP")
        desc = mcp_payload["description"]
        self.assertEqual(desc["en"], "Desc EN")
        self.assertEqual(desc["es"], "Desc ES")
        self.assertEqual(desc["pt"], "Desc PT")
        cfg_by_name = {c["name"]: c for c in mcp_payload["config"]}
        self.assertTrue(cfg_by_name["REQ_FIELD"]["is_required"])
        self.assertFalse(cfg_by_name["OPT_FIELD"]["is_required"])


class CatalogRowKeyParityTestCase(TestCase):
    """My-agents, team, and v1 official group rows share the same catalog keys."""

    def setUp(self):
        from nexus.inline_agents.api.serializers.catalog import CATALOG_ROW_KEYS

        self.expected_keys = CATALOG_ROW_KEYS
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.group = AgentGroup.objects.create(name="Parity Group", slug="parity-group-unique", shared_config={})
        AgentGroupModal.objects.create(group=self.group, agent_name="Parity Display")
        self.agent = InlineAgent.objects.create(
            name="Parity Template",
            slug="parity-agent-unique",
            instruction="i",
            collaboration_instructions="about en",
            foundation_model="m:v",
            project=self.project,
            group=self.group,
            is_official=True,
            source_type=InlineAgent.PLATFORM,
        )
        Version.objects.create(skills=[], display_skills=[], agent=self.agent)
        IntegratedAgent.objects.create(agent=self.agent, project=self.project)

    def _assert_catalog_row_keys(self, row: dict) -> None:
        self.assertEqual(frozenset(row.keys()), self.expected_keys)
        self.assertNotIn("agents", row)
        self.assertNotIn("last_updated", row)

    def _assert_my_agents_row_keys(self, row: dict) -> None:
        from nexus.inline_agents.api.serializers.catalog import MY_AGENTS_LAST_UPDATED_KEY

        self.assertEqual(frozenset(row.keys()), self.expected_keys | {MY_AGENTS_LAST_UPDATED_KEY})
        self.assertNotIn("agents", row)

    def test_my_agents_uses_catalog_row_keys(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        project_uuid = str(self.project.uuid)

        my_resp = client.get(reverse("my-agents", kwargs={"project_uuid": project_uuid}))
        my_resp.render()
        my_row = next(r for r in json.loads(my_resp.content) if r["uuid"] == str(self.agent.uuid))
        self._assert_my_agents_row_keys(my_row)

    def test_team_roster_includes_last_updated(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        project_uuid = str(self.project.uuid)

        team_resp = client.get(reverse("teams", kwargs={"project_uuid": project_uuid}))
        team_resp.render()
        team_row = next(r for r in json.loads(team_resp.content)["agents"] if r["uuid"] == str(self.agent.uuid))
        self.assertIn("last_updated", team_row)
        self.assertIsNotNone(team_row["last_updated"])

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_v1_official_group_row_matches_custom_agent_row_keys(self, mock_has_permission):
        mock_has_permission.return_value = True
        client = APIClient()
        client.force_authenticate(user=self.user)
        project_uuid = str(self.project.uuid)

        my_resp = client.get(reverse("my-agents", kwargs={"project_uuid": project_uuid}))
        my_resp.render()
        my_row = next(r for r in json.loads(my_resp.content) if r["uuid"] == str(self.agent.uuid))

        list_url = reverse("v1-official-agents")
        resp = client.get(
            list_url,
            {"project_uuid": project_uuid, "group": self.group.slug},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(resp.status_code, 200)
        group_row = next(r for r in _official_v1_grouped_rows(resp.json()) if r["group"] == self.group.slug)
        self._assert_catalog_row_keys(group_row)
        self.assertEqual(group_row["name"], "Parity Display")
        self._assert_my_agents_row_keys(my_row)
        self.assertNotIn("last_updated", group_row)


class OfficialAvailableSystemsV1TestCase(TestCase):
    """GET /api/v1/official/available-systems and list payload without embedded available_systems."""

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_available_systems_returns_envelope(self, mock_has_permission):
        mock_has_permission.return_value = True

        target_project = ProjectFactory()
        user = target_project.created_by
        slug = "avail-systems-api-test-unique"
        AgentSystem.objects.create(name="API Test System", slug=slug)

        client = APIClient()
        client.force_authenticate(user=user)
        url = reverse("v1-official-available-systems")
        response = client.get(
            url,
            {"project_uuid": str(target_project.uuid)},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("available_systems", body)
        slugs = [s["slug"] for s in body["available_systems"]]
        self.assertIn(slug, slugs)

    def test_available_systems_forbidden_without_project_uuid_for_project_bearer(self):
        """Bearer tokens outside EXTERNAL_SUPERUSERS_TOKENS require project_uuid (ProjectPermission)."""
        target_project = ProjectFactory()
        user = target_project.created_by

        client = APIClient()
        client.force_authenticate(user=user)
        url = reverse("v1-official-available-systems")
        response = client.get(url, HTTP_AUTHORIZATION="Bearer test-token")
        self.assertEqual(response.status_code, 403)

    @mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
    def test_official_agents_list_new_object_has_no_available_systems(self, mock_has_permission):
        mock_has_permission.return_value = True

        target_project = ProjectFactory()
        user = target_project.created_by

        client = APIClient()
        client.force_authenticate(user=user)
        list_url = reverse("v1-official-agents")
        resp = client.get(
            list_url,
            {"project_uuid": str(target_project.uuid)},
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(resp.status_code, 200)
        new_payload = resp.json()["new"]
        self.assertNotIn("available_systems", new_payload)
        self.assertIn("agents", new_payload)


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


class InlineTraceResponseRemapTestCase(TestCase):
    """API-only remap of ``trace.config.agentName`` (slug → list display name)."""

    def test_remap_leaves_manager_unchanged_and_resolves_agent_slug(self):
        from nexus.agents.api.inline_trace_response import remap_inline_traces_config_agent_names

        project = ProjectFactory()
        InlineAgent.objects.create(
            name="Template VTEX (catalog)",
            slug="product_concierge_catalog",
            instruction="i",
            collaboration_instructions="collab",
            foundation_model="m:v",
            project=project,
        )
        traces = [
            {"trace": {"config": {"agentName": "manager", "type": "x", "toolName": ""}, "trace": {}}},
            {"trace": {"config": {"agentName": "product_concierge_catalog", "type": "y", "toolName": ""}, "trace": {}}},
        ]
        out = remap_inline_traces_config_agent_names(traces, project_uuid=str(project.uuid))
        self.assertEqual(out[0]["trace"]["config"]["agentName"], "manager")
        self.assertEqual(out[1]["trace"]["config"]["agentName"], "Template VTEX")

    def test_remap_invalid_project_uuid_leaves_slugs_unchanged(self):
        from nexus.agents.api.inline_trace_response import remap_inline_traces_config_agent_names

        project = ProjectFactory()
        InlineAgent.objects.create(
            name="Template VTEX (catalog)",
            slug="product_concierge_catalog",
            instruction="i",
            collaboration_instructions="collab",
            foundation_model="m:v",
            project=project,
        )
        traces = [
            {"trace": {"config": {"agentName": "product_concierge_catalog", "type": "y", "toolName": ""}, "trace": {}}},
        ]
        out = remap_inline_traces_config_agent_names(traces, project_uuid="not-a-uuid")
        self.assertEqual(out[0]["trace"]["config"]["agentName"], "product_concierge_catalog")

    def test_remap_resolves_slug_when_trace_casing_differs_from_db(self):
        from nexus.agents.api.inline_trace_response import remap_inline_traces_config_agent_names

        project = ProjectFactory()
        InlineAgent.objects.create(
            name="Template VTEX (catalog)",
            slug="product_concierge_catalog",
            instruction="i",
            collaboration_instructions="collab",
            foundation_model="m:v",
            project=project,
        )
        traces = [
            {"trace": {"config": {"agentName": "Product_Concierge_Catalog", "type": "y", "toolName": ""}, "trace": {}}},
        ]
        out = remap_inline_traces_config_agent_names(traces, project_uuid=str(project.uuid))
        self.assertEqual(out[0]["trace"]["config"]["agentName"], "Template VTEX")

    def test_remap_flat_websocket_trace_payload(self):
        from nexus.agents.api.inline_trace_response import remap_inline_trace_for_preview_websocket

        project = ProjectFactory()
        InlineAgent.objects.create(
            name="Template VTEX (catalog)",
            slug="product_concierge_catalog",
            instruction="i",
            collaboration_instructions="collab",
            foundation_model="m:v",
            project=project,
        )
        trace = {
            "config": {"agentName": "product_concierge_catalog", "type": "y", "toolName": ""},
            "trace": {},
        }
        out = remap_inline_trace_for_preview_websocket(trace, project_uuid=str(project.uuid))
        self.assertEqual(out["config"]["agentName"], "Template VTEX")
