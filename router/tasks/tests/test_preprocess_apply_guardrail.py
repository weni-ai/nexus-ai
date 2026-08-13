from unittest.mock import patch

from django.test import SimpleTestCase

from router.tasks.invoke import UnsafeMessageException, _preprocess_message_input


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
