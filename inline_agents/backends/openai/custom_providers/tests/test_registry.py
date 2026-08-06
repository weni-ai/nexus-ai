from django.test import SimpleTestCase

from inline_agents.backends.openai.agent_entities import AgentModel
from inline_agents.backends.openai.custom_providers.registry import (
    get_registered_vendors,
    resolve_custom_model,
)
from inline_agents.backends.openai.custom_providers.whirlpool import (
    WHIRLPOOL_MODEL_ID,
    WhirlpoolModel,
)


class CustomProviderRegistryTests(SimpleTestCase):
    def test_whirlpool_vendor_registered(self):
        self.assertIn("whirlpool", get_registered_vendors())

    def test_resolve_by_model_vendor(self):
        model = resolve_custom_model(
            "gpt-4",
            {"client_id": "id", "client_secret": "secret"},
            model_vendor="whirlpool",
        )
        self.assertIsInstance(model, WhirlpoolModel)

    def test_resolve_by_custom_prefix(self):
        model = resolve_custom_model(
            WHIRLPOOL_MODEL_ID,
            {"client_id": "id", "client_secret": "secret"},
        )
        self.assertIsInstance(model, WhirlpoolModel)

    def test_unknown_vendor_returns_none(self):
        self.assertIsNone(resolve_custom_model("gpt-4", {}, model_vendor="unknown_vendor_xyz"))

    def test_agent_model_get_model_prefers_custom_over_litellm(self):
        resolved = AgentModel().get_model(
            WHIRLPOOL_MODEL_ID,
            {"client_id": "id", "client_secret": "secret"},
            model_vendor="whirlpool",
        )
        self.assertIsInstance(resolved, WhirlpoolModel)

    def test_agent_model_get_model_keeps_litellm_path(self):
        from agents.extensions.models.litellm_model import LitellmModel

        resolved = AgentModel().get_model(
            "litellm/openai/gpt-4o",
            {"api_key": "sk-test", "api_base": "https://example.com"},
            model_vendor="openai",
        )
        self.assertIsInstance(resolved, LitellmModel)
        self.assertEqual(resolved.model, "openai/gpt-4o")

    def test_agent_model_get_model_plain_string(self):
        resolved = AgentModel().get_model("gpt-4o-mini", {}, model_vendor="openai")
        self.assertEqual(resolved, "gpt-4o-mini")
