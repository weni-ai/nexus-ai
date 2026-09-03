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
        self.assertEqual(MCPConfigOption.objects.filter(mcp=self.mcp).count(), 0)

    def test_full_replace_removes_stale_credential_templates(self):
        MCPCredentialTemplate.objects.create(
            mcp=self.mcp,
            name="URL_IMAGEM_LOTOFACIL",
            label="URL imagem Lotofácil",
            placeholder="https://cdn.example.com/lotofacil.png",
            is_confidential=False,
        )
        MCPCredentialTemplate.objects.create(
            mcp=self.mcp,
            name="BASE_URL",
            label="Old VTEX",
            placeholder="old",
            is_confidential=True,
        )
        MCPConfigOption.objects.create(
            mcp=self.mcp,
            name="LEGACY_OPTION",
            label="Legacy",
            type=MCPConfigOption.TEXT,
            default_value="x",
            options=[],
        )

        sync_mcp_templates_from_agent_payload(
            self.mcp,
            {
                "BASE_URL": {"label": "VTEX Account", "placeholder": "your-store", "is_confidential": False},
                "STORE_URL": {
                    "label": "Store Domain URL",
                    "placeholder": "https://www.your-store.com",
                    "is_confidential": False,
                },
            },
            {
                "DISPLAY_MODE": {
                    "label": "Send WhatsApp Catalog",
                    "type": "radio",
                    "options": [{"label": "Enabled", "value": "true"}],
                    "default": "false",
                    "required": True,
                }
            },
        )

        cred_names = set(MCPCredentialTemplate.objects.filter(mcp=self.mcp).values_list("name", flat=True))
        self.assertEqual(cred_names, {"BASE_URL", "STORE_URL"})
        base = MCPCredentialTemplate.objects.get(mcp=self.mcp, name="BASE_URL")
        self.assertEqual(base.label, "VTEX Account")
        self.assertFalse(base.is_confidential)

        opts = list(MCPConfigOption.objects.filter(mcp=self.mcp))
        self.assertEqual(len(opts), 1)
        self.assertEqual(opts[0].name, "DISPLAY_MODE")
        self.assertEqual(opts[0].type, MCPConfigOption.RADIO)
        self.assertEqual(opts[0].default_value, "false")
        self.assertEqual(opts[0].options, [{"name": "Enabled", "value": "true"}])
        self.assertTrue(opts[0].is_required)

    def test_credentials_only_clears_config_options(self):
        MCPConfigOption.objects.create(
            mcp=self.mcp,
            name="DISPLAY_MODE",
            label="Send catalog",
            type=MCPConfigOption.RADIO,
            default_value="false",
            options=[{"name": "Enabled", "value": "true"}],
        )
        sync_mcp_templates_from_agent_payload(
            self.mcp,
            {"BASE_URL": {"label": "VTEX Account", "placeholder": "store", "is_confidential": False}},
            None,
        )
        self.assertTrue(MCPCredentialTemplate.objects.filter(mcp=self.mcp, name="BASE_URL").exists())
        self.assertEqual(MCPConfigOption.objects.filter(mcp=self.mcp).count(), 0)

    def test_constants_only_clears_credential_templates(self):
        MCPCredentialTemplate.objects.create(
            mcp=self.mcp,
            name="BASE_URL",
            label="VTEX Account",
            placeholder="store",
            is_confidential=False,
        )
        sync_mcp_templates_from_agent_payload(
            self.mcp,
            None,
            {
                "TRADE_POLICY": {
                    "label": "Trade Policy (sc)",
                    "type": "text",
                    "default": "1",
                }
            },
        )
        self.assertEqual(MCPCredentialTemplate.objects.filter(mcp=self.mcp).count(), 0)
        opt = MCPConfigOption.objects.get(mcp=self.mcp, name="TRADE_POLICY")
        self.assertEqual(opt.label, "Trade Policy (sc)")
        self.assertEqual(opt.default_value, "1")

    def test_empty_payload_clears_both_tables(self):
        MCPCredentialTemplate.objects.create(
            mcp=self.mcp,
            name="BASE_URL",
            label="VTEX Account",
            placeholder="store",
            is_confidential=False,
        )
        MCPConfigOption.objects.create(
            mcp=self.mcp,
            name="DISPLAY_MODE",
            label="Send catalog",
            type=MCPConfigOption.TEXT,
            default_value="false",
            options=[],
        )
        sync_mcp_templates_from_agent_payload(self.mcp, None, None)
        self.assertEqual(MCPCredentialTemplate.objects.filter(mcp=self.mcp).count(), 0)
        self.assertEqual(MCPConfigOption.objects.filter(mcp=self.mcp).count(), 0)

    def test_scalar_constant_creates_text_option(self):
        sync_mcp_templates_from_agent_payload(self.mcp, None, {"DISPLAY_MODE": "true"})
        opt = MCPConfigOption.objects.get(mcp=self.mcp, name="DISPLAY_MODE")
        self.assertEqual(opt.type, MCPConfigOption.TEXT)
        self.assertEqual(opt.default_value, "true")
        self.assertEqual(opt.label, "DISPLAY_MODE")

    def test_empty_constant_dict_does_not_create_row(self):
        sync_mcp_templates_from_agent_payload(self.mcp, None, {"UNUSED": {}})
        self.assertFalse(MCPConfigOption.objects.filter(mcp=self.mcp, name="UNUSED").exists())
