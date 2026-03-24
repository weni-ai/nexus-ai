import json
import unittest

from router.tasks.sqs_message_events import merge_sqs_outgoing_text, sqs_response_text_from_agent_output


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


class TestMergeSqsOutgoingText(unittest.TestCase):
    def test_tool_messages_only_when_base_empty(self):
        self.assertEqual(
            merge_sqs_outgoing_text("", skip_dispatch=False, tool_messages_text="from tool"),
            "from tool",
        )

    def test_base_only_when_no_tool_messages(self):
        self.assertEqual(
            merge_sqs_outgoing_text("final answer", skip_dispatch=False, tool_messages_text=""),
            "final answer",
        )

    def test_combines_tool_then_base(self):
        self.assertEqual(
            merge_sqs_outgoing_text("final", skip_dispatch=False, tool_messages_text="tool line"),
            "tool line\n\nfinal",
        )

    def test_skip_dispatch_base_with_tool_prefix(self):
        raw = json.dumps(
            {"is_final_output": True, "messages": [{"text": "done"}]},
            ensure_ascii=False,
        )
        self.assertEqual(
            merge_sqs_outgoing_text(raw, skip_dispatch=True, tool_messages_text="earlier"),
            "earlier\n\ndone",
        )
