import json
import unittest

from router.tasks.sqs_message_events import sqs_response_text_from_agent_output


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
