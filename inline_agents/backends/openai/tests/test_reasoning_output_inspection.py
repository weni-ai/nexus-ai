from django.test import SimpleTestCase

from inline_agents.backends.openai.hooks import (
    extract_first_message_text_from_response,
    inspect_llm_response_output_for_reasoning,
    should_emit_message_interim_fallback,
)


class _Item:
    def __init__(self, type, summary=None, content=None):
        self.type = type
        self.summary = summary
        self.content = content


class _ContentPart:
    def __init__(self, text):
        self.text = text


class TestInspectLlmResponseOutputForReasoning(SimpleTestCase):
    def test_empty_output(self):
        result = inspect_llm_response_output_for_reasoning(type("R", (), {"output": []})())

        self.assertEqual(result["output_types"], [])
        self.assertEqual(result["reasoning_items"], 0)
        self.assertEqual(result["reasoning_with_summary"], 0)
        self.assertEqual(result["reasoning_summary_shapes"], [])
        self.assertEqual(result["message_items"], 0)
        self.assertEqual(result["message_with_text"], 0)
        self.assertEqual(result["message_text_chars"], 0)
        self.assertEqual(result["function_call_items"], 0)

    def test_counts_reasoning_with_and_without_summary(self):
        response = type(
            "R",
            (),
            {
                "output": [
                    _Item("reasoning", summary=[{"text": "checking cep"}]),
                    _Item("function_call"),
                    _Item("reasoning", summary=None),
                ]
            },
        )()

        result = inspect_llm_response_output_for_reasoning(response)

        self.assertEqual(result["output_types"], ["reasoning", "function_call", "reasoning"])
        self.assertEqual(result["reasoning_items"], 2)
        self.assertEqual(result["reasoning_with_summary"], 1)
        self.assertEqual(
            result["reasoning_summary_shapes"],
            ["list_len=1_text_chars=12", "none"],
        )
        self.assertEqual(result["function_call_items"], 1)

    def test_classifies_empty_list_summary(self):
        result = inspect_llm_response_output_for_reasoning({"output": [{"type": "reasoning", "summary": []}]})

        self.assertEqual(result["reasoning_items"], 1)
        self.assertEqual(result["reasoning_with_summary"], 0)
        self.assertEqual(result["reasoning_summary_shapes"], ["empty_list"])

    def test_classifies_list_with_empty_text_parts(self):
        result = inspect_llm_response_output_for_reasoning(
            {"output": [{"type": "reasoning", "summary": [{"text": ""}, {"text": None}]}]}
        )

        self.assertEqual(result["reasoning_summary_shapes"], ["list_len=2_no_text"])

    def test_message_with_text_alongside_function_call(self):
        response = type(
            "R",
            (),
            {
                "output": [
                    _Item("reasoning", summary=None),
                    _Item("message", content=[_ContentPart("Vou verificar o CEP")]),
                    _Item("function_call"),
                ]
            },
        )()

        result = inspect_llm_response_output_for_reasoning(response)

        self.assertEqual(result["message_items"], 1)
        self.assertEqual(result["message_with_text"], 1)
        self.assertEqual(result["message_text_chars"], 19)
        self.assertEqual(result["function_call_items"], 1)
        self.assertEqual(result["reasoning_summary_shapes"], ["none"])

    def test_dict_shaped_response(self):
        result = inspect_llm_response_output_for_reasoning(
            {
                "output": [
                    {"type": "message", "content": [{"text": "ok"}]},
                    {"type": "reasoning", "summary": [{"text": "ok"}]},
                ]
            }
        )

        self.assertEqual(result["reasoning_items"], 1)
        self.assertEqual(result["reasoning_with_summary"], 1)
        self.assertEqual(result["message_items"], 1)
        self.assertEqual(result["message_with_text"], 1)
        self.assertEqual(result["message_text_chars"], 2)


class TestMessageInterimFallback(SimpleTestCase):
    def test_extracts_first_message_text(self):
        response = type(
            "R",
            (),
            {
                "output": [
                    _Item("reasoning", summary=[]),
                    _Item("message", content=[_ContentPart("Vou verificar o CEP")]),
                    _Item("function_call"),
                ]
            },
        )()

        self.assertEqual(extract_first_message_text_from_response(response), "Vou verificar o CEP")

    def test_should_emit_when_components_and_empty_summary_with_message_and_tool(self):
        inspection = {
            "reasoning_with_summary": 0,
            "function_call_items": 1,
            "message_with_text": 1,
        }
        self.assertTrue(
            should_emit_message_interim_fallback(
                use_components=True,
                rationale_switch=True,
                turn_off_rationale=False,
                inspection=inspection,
                emitted_from_reasoning_summary=False,
            )
        )

    def test_should_not_emit_without_components(self):
        inspection = {
            "reasoning_with_summary": 0,
            "function_call_items": 1,
            "message_with_text": 1,
        }
        self.assertFalse(
            should_emit_message_interim_fallback(
                use_components=False,
                rationale_switch=True,
                turn_off_rationale=False,
                inspection=inspection,
                emitted_from_reasoning_summary=False,
            )
        )

    def test_should_not_emit_when_summary_already_emitted(self):
        inspection = {
            "reasoning_with_summary": 0,
            "function_call_items": 1,
            "message_with_text": 1,
        }
        self.assertFalse(
            should_emit_message_interim_fallback(
                use_components=True,
                rationale_switch=True,
                turn_off_rationale=False,
                inspection=inspection,
                emitted_from_reasoning_summary=True,
            )
        )

    def test_should_not_emit_without_function_call(self):
        inspection = {
            "reasoning_with_summary": 0,
            "function_call_items": 0,
            "message_with_text": 1,
        }
        self.assertFalse(
            should_emit_message_interim_fallback(
                use_components=True,
                rationale_switch=True,
                turn_off_rationale=False,
                inspection=inspection,
                emitted_from_reasoning_summary=False,
            )
        )
