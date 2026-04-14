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

    def test_scalar_constant_only_updates_default_preserves_type_and_options(self):
        MCPConfigOption.objects.create(
            mcp=self.mcp,
            name="DISPLAY_MODE",
            label="Send catalog",
            type=MCPConfigOption.RADIO,
            default_value="false",
            options=[{"name": "Enabled", "value": "true"}],
        )
        sync_mcp_templates_from_agent_payload(self.mcp, None, {"DISPLAY_MODE": "true"})
        opt = MCPConfigOption.objects.get(mcp=self.mcp, name="DISPLAY_MODE")
        self.assertEqual(opt.type, MCPConfigOption.RADIO)
        self.assertEqual(opt.default_value, "true")
        self.assertEqual(opt.options, [{"name": "Enabled", "value": "true"}])
        self.assertEqual(opt.label, "Send catalog")

    def test_dict_without_default_preserves_existing_default_value(self):
        MCPConfigOption.objects.create(
            mcp=self.mcp,
            name="TRADE_POLICY",
            label="Old label",
            type=MCPConfigOption.TEXT,
            default_value="1",
            options=[],
        )
        sync_mcp_templates_from_agent_payload(
            self.mcp,
            None,
            {"TRADE_POLICY": {"label": "Trade Policy (sc)"}},
        )
        opt = MCPConfigOption.objects.get(mcp=self.mcp, name="TRADE_POLICY")
        self.assertEqual(opt.default_value, "1")
        self.assertEqual(opt.label, "Trade Policy (sc)")
        self.assertEqual(opt.type, MCPConfigOption.TEXT)

    def test_empty_constant_dict_does_not_create_row(self):
        sync_mcp_templates_from_agent_payload(self.mcp, None, {"UNUSED": {}})
        self.assertFalse(MCPConfigOption.objects.filter(mcp=self.mcp, name="UNUSED").exists())
