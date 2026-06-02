from django.test import TestCase

from nexus.inline_agents.api.official_agents_helpers import (
    get_all_mcps_for_group,
    get_all_systems_for_group,
    group_mcps_for_system,
)
from nexus.inline_agents.api.serializers.catalog import build_official_group_row
from nexus.inline_agents.models import MCP, Agent, AgentGroup, AgentSystem
from nexus.projects.tests.factories import ProjectFactory


class OfficialAgentsHelpersSystemsTestCase(TestCase):
    def test_group_without_agent_system_uses_empty_systems_and_null_mcp_system(self):
        group = AgentGroup.objects.create(name="Feedback", slug="feedback-no-system-test", shared_config={})
        mcp = MCP.objects.create(name="csat", slug="csat-no-system-test", system=None, is_active=True)
        group.mcps.add(mcp)

        self.assertEqual(get_all_systems_for_group(group.slug), [])

        buckets = get_all_mcps_for_group(group.slug)
        self.assertIn(None, buckets)
        self.assertIsNone(buckets[None][0]["system"])
        self.assertNotIn("no_system", buckets)
        self.assertEqual(group_mcps_for_system(buckets, None), buckets[None])
        self.assertEqual(group_mcps_for_system(buckets, ""), buckets[None])

        project = ProjectFactory()
        agent = Agent.objects.create(
            name="Feedback Agent",
            slug="feedback-agent-no-system-test",
            instruction="i",
            collaboration_instructions="c",
            foundation_model="m:v",
            project=project,
            group=group,
            is_official=True,
            source_type=Agent.PLATFORM,
        )
        row = build_official_group_row([agent], group.slug, None)
        self.assertIsNone(row["systems"])
        self.assertIsNone(row["mcps"][0]["system"])

    def test_group_with_agent_system_lists_slug_only(self):
        group = AgentGroup.objects.create(name="VTEX Group", slug="vtex-system-test", shared_config={})
        system = AgentSystem.objects.create(name="VTEX", slug="vtex")
        mcp = MCP.objects.create(name="default", slug="vtex-mcp-test", system=system, is_active=True)
        group.mcps.add(mcp)

        self.assertEqual(get_all_systems_for_group(group.slug), ["vtex"])
        buckets = get_all_mcps_for_group(group.slug)
        self.assertEqual(buckets["vtex"][0]["system"], "vtex")
