import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import SimpleTestCase

from inline_agents.backends.openai.message_context import (
    DEFAULT_CONTEXT_TOOL_NAME,
    extract_message_context,
    inject_context_as_tool_result,
)
from router.tasks.invoke import (
    UnsafeMessageException,
    _extract_and_apply_message_context,
    _preprocess_message_input,
)


class PreprocessApplyGuardrailTestCase(SimpleTestCase):
    @patch("nexus.usecases.guardrails.project_guardrails_config.ProjectGuardrailsConfigUseCase.apply_input_guardrail")
    def test_raises_unsafe_message_on_intervene(self, mock_apply):
        mock_apply.return_value = "Project blocked this topic"
        message = {"text": "politics question", "attachments": [], "metadata": {}}

        with self.assertRaises(UnsafeMessageException) as ctx:
            _preprocess_message_input(
                message,
                "OpenAIBackend",
                guardrails_config={"has_blocked_category": True},
            )

        self.assertEqual(ctx.exception.message, "Project blocked this topic")
        mock_apply.assert_called_once_with("politics question", {"has_blocked_category": True})

    @patch("router.tasks.invoke.complexity_layer")
    @patch("nexus.usecases.guardrails.project_guardrails_config.ProjectGuardrailsConfigUseCase.apply_input_guardrail")
    def test_pass_through_when_allowed(self, mock_apply, mock_complexity):
        mock_apply.return_value = None
        mock_complexity.return_value = None
        message = {"text": "hello", "attachments": [], "metadata": {}}

        processed, foundation_model, _ = _preprocess_message_input(
            message,
            "BedrockBackend",
            guardrails_config={"has_blocked_category": True, "guardrailIdentifier": "gr-1"},
        )

        self.assertEqual(processed["text"], "hello")
        self.assertIsNone(foundation_model)
        mock_apply.assert_called_once_with(
            "hello",
            {"has_blocked_category": True, "guardrailIdentifier": "gr-1"},
        )

    @patch("nexus.usecases.guardrails.project_guardrails_config.ProjectGuardrailsConfigUseCase.apply_input_guardrail")
    def test_does_not_call_guardrails_layer_lambda(self, mock_apply):
        mock_apply.return_value = None
        message = {"text": "hello", "attachments": [], "metadata": {}}

        with patch("router.tasks.invoke.boto3.client") as mock_boto:
            _preprocess_message_input(message, "OpenAIBackend", guardrails_config=None)
            mock_boto.assert_not_called()

        mock_apply.assert_called_once_with("hello", None)

    @patch("nexus.usecases.guardrails.project_guardrails_config.ProjectGuardrailsConfigUseCase.apply_input_guardrail")
    def test_evaluates_composed_text_including_metadata(self, mock_apply):
        mock_apply.return_value = None
        message = {
            "text": "safe",
            "attachments": ["https://example.com/a.png"],
            "metadata": {
                "order": {"product_items": [{"sku": "1"}]},
                "overwrite_message": "blocked politics payload",
            },
        }

        _preprocess_message_input(
            message,
            "OpenAIBackend",
            guardrails_config={"has_blocked_category": True},
        )

        composed_text = mock_apply.call_args.args[0]
        self.assertIn("safe", composed_text)
        self.assertIn("https://example.com/a.png", composed_text)
        self.assertIn("product items", composed_text)
        self.assertIn("blocked politics payload", composed_text)

    @patch("nexus.usecases.guardrails.project_guardrails_config.ProjectGuardrailsConfigUseCase.apply_input_guardrail")
    def test_empty_text_with_ig_comment_overwrite_reaches_agent(self, mock_apply):
        mock_apply.return_value = None
        message = {
            "text": "",
            "attachments": [],
            "metadata": {
                "overwrite_message": {
                    "ig_comment": {
                        "id": "30065221",
                        "media": {"id": "180615383", "caption": "Summer sale post"},
                    }
                }
            },
        }

        processed, _, _ = _preprocess_message_input(message, "OpenAIBackend", guardrails_config=None)

        user_text, context = extract_message_context(processed["text"])
        self.assertEqual(user_text, "")
        self.assertNotIn("overwrite message", processed["text"])
        self.assertIn("30065221", context)
        self.assertIn("ig_comment", context)
        mock_apply.assert_called_once()
        self.assertIn("30065221", mock_apply.call_args.args[0])

    @patch("nexus.usecases.guardrails.project_guardrails_config.ProjectGuardrailsConfigUseCase.apply_input_guardrail")
    def test_structured_overwrite_reaches_agent_as_get_context(self, mock_apply):
        mock_apply.return_value = None
        message = {
            "text": "Sim",
            "attachments": [],
            "metadata": {
                "overwrite_message": {"button": {"payload": "Sim", "text": "Sim"}},
            },
        }

        processed, _, _ = _preprocess_message_input(message, "OpenAIBackend", guardrails_config=None)

        user_text, context = extract_message_context(processed["text"])
        self.assertEqual(user_text, "Sim")
        self.assertEqual(context, '{"button": {"payload": "Sim", "text": "Sim"}}')

    @patch("nexus.usecases.guardrails.project_guardrails_config.ProjectGuardrailsConfigUseCase.apply_input_guardrail")
    def test_instagram_comment_metadata_is_get_context_not_user_message(self, mock_apply):
        """The trace must keep the comment text, and the dict must arrive as get_context."""
        mock_apply.return_value = None
        message = {
            "text": "❤️",
            "attachments": [],
            "metadata": {
                "overwrite_message": {
                    "ig_comment": {
                        "id": "18125199286854738",
                        "media": {"id": "18035070596307290", "media_product_type": "FEED"},
                    },
                    "ig_response_type": "dm_comment",
                }
            },
        }

        processed, _, _ = _preprocess_message_input(message, "OpenAIBackend", guardrails_config=None)
        message_obj = SimpleNamespace(text=processed["text"])
        injected = _extract_and_apply_message_context(message_obj)

        self.assertEqual(message_obj.text, "❤️")
        self.assertNotIn("overwrite message", message_obj.text)
        self.assertNotIn("ig_comment", message_obj.text)
        self.assertIn("18125199286854738", injected)
        self.assertIn("dm_comment", injected)

        session = MagicMock()
        session.add_items = AsyncMock()
        asyncio.run(inject_context_as_tool_result(session, injected))

        function_call, function_output = session.add_items.await_args.args[0]
        self.assertEqual(function_call["name"], DEFAULT_CONTEXT_TOOL_NAME)
        self.assertEqual(function_output["output"], injected)
        self.assertNotIn("❤️", function_output["output"])
