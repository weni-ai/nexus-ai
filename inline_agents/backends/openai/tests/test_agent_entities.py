from agents.extensions.models.litellm_model import LitellmModel
from django.test import SimpleTestCase

from inline_agents.backends.openai.agent_entities import (
    _final_output_from_tool_dict,
    build_reasoning_settings,
    resolve_agent_model,
    supports_reasoning_mode,
)
from inline_agents.backends.openai.prompt_cache import PromptCachingOpenAIResponsesModel


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

    def test_mantle_model_skips_litellm(self):
        self.assertEqual(resolve_agent_model("openai.gpt-5.6-luna", {}), "openai.gpt-5.6-luna")

    def test_mantle_manager_uses_prompt_caching_responses_model(self):
        model = resolve_agent_model(
            "openai.gpt-5.6-luna",
            {},
            model_vendor="aws_mantle",
        )

        self.assertIsInstance(model, PromptCachingOpenAIResponsesModel)
        self.assertEqual(model.model, "openai.gpt-5.6-luna")

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


class BuildReasoningSettingsTests(SimpleTestCase):
    def test_omits_blank_mode(self):
        reasoning = build_reasoning_settings(
            model_has_reasoning=True,
            reasoning_effort="low",
            reasoning_summary="auto",
            reasoning_mode=None,
        )

        self.assertEqual(reasoning.effort, "low")
        self.assertEqual(reasoning.summary, "auto")
        self.assertNotIn("mode", reasoning.model_dump(exclude_unset=True))

    def test_omits_empty_mode(self):
        reasoning = build_reasoning_settings(
            model_has_reasoning=True,
            reasoning_effort="low",
            reasoning_summary="auto",
            reasoning_mode="",
        )

        self.assertEqual(reasoning.effort, "low")
        self.assertNotIn("mode", reasoning.model_dump(exclude_unset=True))

    def test_includes_mode_when_set(self):
        reasoning = build_reasoning_settings(
            model_has_reasoning=True,
            reasoning_effort="none",
            reasoning_summary="auto",
            reasoning_mode="minimal",
        )

        self.assertEqual(reasoning.effort, "none")
        self.assertEqual(reasoning.mode, "minimal")
        self.assertEqual(reasoning.model_dump(exclude_unset=True)["mode"], "minimal")

    def test_returns_none_when_no_reasoning_fields(self):
        self.assertIsNone(build_reasoning_settings())

    def test_omits_mode_for_luna_on_aws_mantle(self):
        reasoning = build_reasoning_settings(
            model_has_reasoning=True,
            reasoning_effort="high",
            reasoning_summary="auto",
            reasoning_mode="pro",
            model="openai.gpt-5.6-luna",
            model_vendor="aws_mantle",
        )

        dumped = reasoning.model_dump(exclude_unset=True)
        self.assertEqual(reasoning.effort, "high")
        self.assertEqual(reasoning.summary, "auto")
        self.assertNotIn("mode", dumped)

    def test_includes_mode_for_luna_on_openai_vendor(self):
        reasoning = build_reasoning_settings(
            model_has_reasoning=True,
            reasoning_effort="high",
            reasoning_summary="auto",
            reasoning_mode="pro",
            model="openai.gpt-5.6-luna",
            model_vendor="OpenAI",
        )

        self.assertEqual(reasoning.mode, "pro")


class SupportsReasoningModeTests(SimpleTestCase):
    def test_luna_on_aws_mantle_is_unsupported(self):
        self.assertFalse(supports_reasoning_mode("openai.gpt-5.6-luna", "aws_mantle"))

    def test_luna_on_openai_vendor_is_supported(self):
        self.assertTrue(supports_reasoning_mode("openai.gpt-5.6-luna", "OpenAI"))

    def test_other_mantle_models_keep_mode(self):
        self.assertTrue(supports_reasoning_mode("openai.gpt-5.4-mini", "aws_mantle"))
