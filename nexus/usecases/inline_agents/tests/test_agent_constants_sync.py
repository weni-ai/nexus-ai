from django.test import TestCase

from nexus.inline_agents.models import Agent, AgentConstant
from nexus.usecases.inline_agents.agent_constants_sync import sync_agent_constants_from_payload
from nexus.usecases.projects.tests.project_factory import ProjectFactory

DISPLAY_MODE = {
    "label": "Send Whatsapp Catalog",
    "type": "radio",
    "options": [{"label": "Enabled", "value": "True"}, {"label": "Disabled", "value": "False"}],
    "default": "False",
    "required": True,
}


class TestSyncAgentConstantsFromPayload(TestCase):
    def setUp(self):
        self.project = ProjectFactory(name="Sync Constants", brain_on=True)
        self.agent_a = Agent.objects.create(
            name="Agent A",
            slug="agent-a-constants",
            instruction="x",
            collaboration_instructions="y",
            project=self.project,
            foundation_model="model:version",
        )
        self.agent_b = Agent.objects.create(
            name="Agent B",
            slug="agent-b-constants",
            instruction="x",
            collaboration_instructions="y",
            project=self.project,
            foundation_model="model:version",
        )

    def test_removing_constant_from_payload_only_unlinks_current_agent(self):
        shared_payload = {"DISPLAY_MODE": DISPLAY_MODE}
        sync_agent_constants_from_payload(self.agent_a, self.project, shared_payload)
        sync_agent_constants_from_payload(self.agent_b, self.project, shared_payload)

        row = AgentConstant.objects.get(project=self.project, key="DISPLAY_MODE")
        self.assertEqual(row.agents.count(), 2)

        sync_agent_constants_from_payload(self.agent_a, self.project, {}, prune_missing=True)

        row.refresh_from_db()
        self.assertTrue(row.agents.filter(pk=self.agent_b.pk).exists())
        self.assertFalse(row.agents.filter(pk=self.agent_a.pk).exists())

    def test_removing_last_linked_agent_deletes_constant_row(self):
        sync_agent_constants_from_payload(self.agent_a, self.project, {"DISPLAY_MODE": DISPLAY_MODE})
        sync_agent_constants_from_payload(self.agent_a, self.project, {}, prune_missing=True)

        self.assertFalse(AgentConstant.objects.filter(project=self.project, key="DISPLAY_MODE").exists())
