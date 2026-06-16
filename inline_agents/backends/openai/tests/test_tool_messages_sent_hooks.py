import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from inline_agents.backends.openai.entities import HooksState
from inline_agents.backends.openai.hooks import _maybe_send_tool_messages_sent_to_conversation


class MaybeSendToolMessagesSentTests(SimpleTestCase):
    def _context_data(self):
        context_data = MagicMock()
        context_data.project.get.return_value = "proj-1"
        context_data.contact.get.side_effect = lambda key, default="": {
            "urn": "urn:1",
            "channel_uuid": "chan-1",
            "name": "Alice",
        }.get(key, default)
        return context_data

    def _hooks_state(self):
        hooks_state = HooksState(agents=[])
        hooks_state.message_conversation_log_uuid = "log-uuid"
        return hooks_state

    @patch("inline_agents.backends.openai.hooks.send_tool_messages_sent_to_conversation_sqs")
    def test_sends_when_messages_sent_without_is_final_output(self, mock_send):
        result = {
            "result": {"message": "compose me", "broadcasts_sent": 2},
            "messages_sent": [{"text": "first"}, {"text": "second"}],
        }
        _maybe_send_tool_messages_sent_to_conversation(
            self._context_data(),
            json.dumps(result),
            preview=False,
            skip_conversation_sqs=False,
            hooks_state=self._hooks_state(),
            tool_name="sendmessages",
        )
        mock_send.assert_called_once_with(
            texts=["first", "second"],
            project_uuid="proj-1",
            contact_urn="urn:1",
            channel_uuid="chan-1",
            contact_name="Alice",
            message_conversation_log_uuid="log-uuid",
            tool_name="sendmessages",
        )

    @patch("inline_agents.backends.openai.hooks.send_tool_messages_sent_to_conversation_sqs")
    def test_skips_when_is_final_output(self, mock_send):
        result = {"is_final_output": True, "messages_sent": [{"text": "a"}]}
        _maybe_send_tool_messages_sent_to_conversation(
            self._context_data(),
            result,
            preview=False,
            skip_conversation_sqs=False,
            hooks_state=self._hooks_state(),
        )
        mock_send.assert_not_called()

    @patch("inline_agents.backends.openai.hooks.send_tool_messages_sent_to_conversation_sqs")
    def test_skips_in_preview(self, mock_send):
        result = {"messages_sent": [{"text": "a"}]}
        _maybe_send_tool_messages_sent_to_conversation(
            self._context_data(),
            result,
            preview=True,
            skip_conversation_sqs=False,
            hooks_state=self._hooks_state(),
        )
        mock_send.assert_not_called()
