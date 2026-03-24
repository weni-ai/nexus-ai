from django.test import SimpleTestCase

from inline_agents.backends.openai.agent_entities import _final_output_from_tool_dict


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
