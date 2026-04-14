from django.test import TestCase

from nexus.inline_agents.models import MCP, AgentSystem, MCPConfigOption, MCPCredentialTemplate
from nexus.usecases.inline_agents.mcp_definition_sync import sync_mcp_templates_from_agent_payload


class TestSyncMcpTemplatesFromAgentPayload(TestCase):
    def setUp(self):
        self.system = AgentSystem.objects.create(name="VTEX", slug="vtex-mcp-sync-test")
        self.mcp = MCP.objects.create(name="Concierge MCP", slug="product-concierge-mcp-sync-test", system=self.system)

    def test_creates_credential_templates(self):
        sync_mcp_templates_from_agent_payload(
            self.mcp,
            {"BASE_URL": {"label": "VTEX Account", "placeholder": "store", "is_confidential": False}},
            None,
        )
        t = MCPCredentialTemplate.objects.get(mcp=self.mcp, name="BASE_URL")
        self.assertEqual(t.label, "VTEX Account")
        self.assertFalse(t.is_confidential)

    def test_updates_existing_config_option_from_yaml_shape(self):
        MCPConfigOption.objects.create(
            mcp=self.mcp,
            name="DISPLAY_MODE",
            label="Old",
            type=MCPConfigOption.TEXT,
            default_value="old",
            options=[],
        )
        constants = {
            "DISPLAY_MODE": {
                "label": "Send WhatsApp Catalog",
                "type": "radio",
                "options": [{"label": "Enabled", "value": "true"}],
                "default": "false",
            }
        }
        sync_mcp_templates_from_agent_payload(self.mcp, None, constants)
        opt = MCPConfigOption.objects.get(mcp=self.mcp, name="DISPLAY_MODE")
        self.assertEqual(opt.type, MCPConfigOption.RADIO)
        self.assertEqual(opt.default_value, "false")
        self.assertEqual(opt.options, [{"name": "Enabled", "value": "true"}])
        self.assertEqual(opt.label, "Send WhatsApp Catalog")
