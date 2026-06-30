from django.test import TestCase

from nexus.inline_agents.api.serializers.catalog import _mcps_for_standalone_agent
from nexus.inline_agents.models import Agent, AgentConstant
from nexus.usecases.inline_agents.create import CreateAgentUseCase
from nexus.usecases.inline_agents.update import UpdateAgentUseCase
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class TestAgentConstantPush(TestCase):
    def setUp(self):
        self.project = ProjectFactory(name="Agent Constants", brain_on=True)
        self.create_usecase = CreateAgentUseCase()
        self.update_usecase = UpdateAgentUseCase()
        self.payload = {
            "name": "Product Concierge Agent",
            "description": "Helps customers discover products from the store catalog.",
            "instructions": ["You help customers find products in the store catalog."],
            "guardrails": ["Do not discuss politics, religion or any other sensitive topic."],
            "credentials": {
                "BASE_URL": {
                    "label": "VTEX Account",
                    "placeholder": "your-store",
                    "is_confidential": False,
                }
            },
            "constants": {
                "DISPLAY_MODE": {
                    "label": "Send Whatsapp Catalog",
                    "type": "radio",
                    "options": [{"label": "Enabled", "value": "True"}, {"label": "Disabled", "value": "False"}],
                    "default": "False",
                    "required": True,
                },
                "MAX_CATALOGS": {
                    "label": "Maximum Catalogs to Send",
                    "type": "text",
                    "max_length": 2,
                    "required": False,
                    "default": "3",
                },
            },
            "tools": [],
        }

    def test_create_agent_persists_agent_constants_without_mcp(self):
        agent = self.create_usecase.create_agent(
            "product_concierge_agent_platform_test",
            self.payload,
            self.project,
            {},
        )

        self.assertEqual(agent.agentconstant_set.count(), 2)
        display_mode = AgentConstant.objects.get(project=self.project, key="DISPLAY_MODE")
        self.assertEqual(display_mode.type, "RADIO")
        self.assertEqual(display_mode.default_value, "False")
        self.assertTrue(display_mode.is_required)
        self.assertEqual(agent.mcps.count(), 0)

    def test_standalone_agent_api_payload_includes_constant_schema(self):
        agent = self.create_usecase.create_agent("cep_agent_constants", self.payload, self.project, {})

        mcps = _mcps_for_standalone_agent(agent)
        self.assertEqual(len(mcps), 1)
        self.assertIsNone(mcps[0]["name"])
        self.assertEqual(len(mcps[0]["config"]), 2)
        config_names = {item["name"] for item in mcps[0]["config"]}
        self.assertEqual(config_names, {"DISPLAY_MODE", "MAX_CATALOGS"})
        self.assertEqual(len(mcps[0]["credentials"]), 1)

    def test_update_agent_syncs_new_constant_definitions(self):
        agent = Agent.objects.create(
            name=self.payload["name"],
            slug="update_constants_agent",
            collaboration_instructions=self.payload["description"],
            project=self.project,
            instruction="x",
            foundation_model="model:version",
        )
        self.create_usecase.create_constants(agent, self.project, self.payload["constants"])

        updated_payload = {
            **self.payload,
            "constants": {
                "MAX_RESULTS": {
                    "label": "Maximum Results",
                    "type": "text",
                    "max_length": 2,
                    "required": False,
                    "default": "5",
                }
            },
        }
        self.update_usecase.update_agent(agent, updated_payload, self.project, {})

        self.assertFalse(AgentConstant.objects.filter(project=self.project, key="DISPLAY_MODE", agents=agent).exists())
        self.assertTrue(AgentConstant.objects.filter(project=self.project, key="MAX_RESULTS", agents=agent).exists())
