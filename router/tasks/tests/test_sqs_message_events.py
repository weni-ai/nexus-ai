import json
import unittest
from unittest.mock import MagicMock, patch

from router.tasks.sqs_message_events import (
    EVENT_TYPE_MESSAGE_SENT,
    extract_messages_sent_texts,
    send_tool_messages_sent_to_conversation_sqs,
    sqs_response_text_from_agent_output,
    tool_result_has_final_output,
)


class TestSqsResponseTextFromAgentOutput(unittest.TestCase):
    def test_skip_dispatch_false_returns_unchanged(self):
        raw = '{"is_final_output": true, "messages_sent": [{"text": "a"}]}'
        self.assertEqual(
            sqs_response_text_from_agent_output(raw, skip_dispatch=False),
            raw,
        )

    def test_skip_dispatch_true_extracts_messages_joined_with_newline(self):
        raw = json.dumps(
            {
                "is_final_output": True,
                "messages_sent": [{"text": " first "}, {"text": "second"}],
            },
            ensure_ascii=False,
        )
        self.assertEqual(
            sqs_response_text_from_agent_output(raw, skip_dispatch=True),
            "first\nsecond",
        )

    def test_skip_dispatch_true_invalid_json_unchanged(self):
        raw = "not json {"
        self.assertEqual(
            sqs_response_text_from_agent_output(raw, skip_dispatch=True),
            raw,
        )

    def test_skip_dispatch_true_empty_response(self):
        self.assertEqual(sqs_response_text_from_agent_output("", skip_dispatch=True), "")

    def test_skip_dispatch_true_messages_empty_list_falls_back_to_response(self):
        raw = '{"is_final_output": true, "messages_sent": []}'
        self.assertEqual(
            sqs_response_text_from_agent_output(raw, skip_dispatch=True),
            raw,
        )

    def test_skip_dispatch_true_all_empty_text_parts_falls_back(self):
        raw = '{"is_final_output": true, "messages_sent": [{"text": ""}, {"text": "   "}]}'
        self.assertEqual(
            sqs_response_text_from_agent_output(raw, skip_dispatch=True),
            raw,
        )

    def test_skip_dispatch_true_merge_style_list_of_channel_msgs(self):
        raw = json.dumps([{"msg": {"text": " Line one "}}, {"msg": {"text": "Two"}}], ensure_ascii=False)
        self.assertEqual(
            sqs_response_text_from_agent_output(raw, skip_dispatch=True),
            "Line one\nTwo",
        )

    def test_skip_dispatch_true_merge_list_non_msg_entries_skipped(self):
        raw = json.dumps([{"msg": {"text": "a"}}, {"other": 1}], ensure_ascii=False)
        self.assertEqual(
            sqs_response_text_from_agent_output(raw, skip_dispatch=True),
            "a",
        )


class TestExtractMessagesSentTexts(unittest.TestCase):
    def test_sendmessages_style_payload_without_is_final_output(self):
        parsed = {
            "result": {"message": "Terceira mensagem", "broadcasts_sent": 2},
            "messages_sent": [
                {"text": "Primeira mensagem genérica enviada via broadcast."},
                {"text": "Segunda mensagem genérica enviada via broadcast."},
            ],
        }
        self.assertEqual(
            extract_messages_sent_texts(parsed),
            [
                "Primeira mensagem genérica enviada via broadcast.",
                "Segunda mensagem genérica enviada via broadcast.",
            ],
        )
        self.assertFalse(tool_result_has_final_output(parsed))

    def test_nested_messages_sent_under_result(self):
        parsed = {
            "result": {
                "is_final_output": False,
                "messages_sent": [{"text": "inner only"}],
            },
        }
        self.assertEqual(extract_messages_sent_texts(parsed), ["inner only"])

    def test_top_level_messages_sent_preferred_over_empty(self):
        parsed = {
            "result": {"messages_sent": [{"text": "inner"}]},
            "messages_sent": [{"text": "top"}],
        }
        self.assertEqual(extract_messages_sent_texts(parsed), ["top"])


class TestToolResultHasFinalOutput(unittest.TestCase):
    def test_top_level_flag(self):
        self.assertTrue(tool_result_has_final_output({"is_final_output": True}))

    def test_nested_flag(self):
        self.assertTrue(
            tool_result_has_final_output({"result": {"is_final_output": True}, "messages_sent": []})
        )

    def test_no_flag(self):
        self.assertFalse(tool_result_has_final_output({"messages_sent": [{"text": "a"}]}))


class TestSendToolMessagesSentToConversationSqs(unittest.TestCase):
    @patch("router.tasks.sqs_message_events.get_conversation_events_producer")
    def test_sends_one_event_per_text(self, mock_get_producer):
        producer = MagicMock()
        mock_get_producer.return_value = producer

        send_tool_messages_sent_to_conversation_sqs(
            texts=["first", "second"],
            project_uuid="proj-1",
            contact_urn="urn:1",
            channel_uuid="chan-1",
            contact_name="Alice",
            message_conversation_log_uuid="log-uuid",
            tool_name="sendmessages",
        )

        self.assertEqual(producer.send_event.call_count, 2)
        first_event = producer.send_event.call_args_list[0][0][0]
        second_event = producer.send_event.call_args_list[1][0][0]
        self.assertEqual(first_event["event_type"], EVENT_TYPE_MESSAGE_SENT)
        self.assertEqual(first_event["data"]["message"]["text"], "first")
        self.assertEqual(first_event["data"]["message"]["id"], "log-uuid:tool:0")
        self.assertEqual(first_event["correlation_id"], "log-uuid:tool:0")
        self.assertEqual(second_event["data"]["message"]["text"], "second")
        self.assertEqual(second_event["data"]["message"]["id"], "log-uuid:tool:1")

    @patch("router.tasks.sqs_message_events.get_conversation_events_producer")
    def test_empty_texts_no_send(self, mock_get_producer):
        send_tool_messages_sent_to_conversation_sqs(
            texts=[],
            project_uuid="proj-1",
            contact_urn="urn:1",
            channel_uuid="chan-1",
            contact_name="Alice",
        )
        mock_get_producer.assert_not_called()
