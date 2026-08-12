from django.test import SimpleTestCase
from agents.extensions.models.litellm_model import LitellmModel

from inline_agents.backends.openai.agent_entities import (
    _final_output_from_tool_dict,
    resolve_agent_model,
)


class FinalOutputFromToolDictTests(SimpleTestCase):
    def test_flat_payload(self):
        parsed = {"is_final_output": True, "messages_sent": [{"text": "a"}]}
        is_final, msgs = _final_output_from_tool_dict(parsed)
        self.assertTrue(is_final)
        self.assertEqual(msgs, [{"text": "a"}])

    def test_lambda_nested_result_flag_top_level_messages(self):
        """Lambda often returns result.is_final_output with messages_sent at top level."""
        parsed = {"result": {"is_final_output": True}, "messages_sent": [{"text": "ola, mundo!"}]}
        is_final, msgs = _final_output_from_tool_dict(parsed)
        self.assertTrue(is_final)
        self.assertEqual(msgs, [{"text": "ola, mundo!"}])

    def test_nested_messages_when_top_empty(self):
        parsed = {
            "result": {"is_final_output": True, "messages_sent": [{"text": "inner"}]},
        }
        is_final, msgs = _final_output_from_tool_dict(parsed)
        self.assertTrue(is_final)
        self.assertEqual(msgs, [{"text": "inner"}])

    def test_nested_false_top_false(self):
        parsed = {"result": {"is_final_output": False}, "messages_sent": []}
        is_final, _ = _final_output_from_tool_dict(parsed)
        self.assertFalse(is_final)


class ResolveAgentModelTests(SimpleTestCase):
    def test_non_litellm_model_returns_string(self):
        self.assertEqual(resolve_agent_model("gpt-4o", {"api_key": "sk"}), "gpt-4o")

    def test_litellm_azure_with_credentials(self):
        credentials = {
            "api_key": "azure-key",
            "api_base": "https://example.openai.azure.com/",
            "api_version": "2024-08-01-preview",
        }
        model = resolve_agent_model("litellm/azure/gpt-4.1", credentials)
        self.assertIsInstance(model, LitellmModel)
        self.assertEqual(model.model, "azure/gpt-4.1")
        self.assertEqual(model.api_key, "azure-key")
        self.assertEqual(model.base_url, "https://example.openai.azure.com/")

    def test_litellm_without_credentials(self):
        model = resolve_agent_model("litellm/azure/gpt-4.1", {})
        self.assertIsInstance(model, LitellmModel)
        self.assertEqual(model.model, "azure/gpt-4.1")
        self.assertIsNone(model.api_key)
        self.assertIsNone(model.base_url)
