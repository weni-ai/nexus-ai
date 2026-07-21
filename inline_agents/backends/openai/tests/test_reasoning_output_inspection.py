from django.test import SimpleTestCase

from inline_agents.backends.openai.hooks import inspect_llm_response_output_for_reasoning


class _Item:
    def __init__(self, type, summary=None):
        self.type = type
        self.summary = summary


class TestInspectLlmResponseOutputForReasoning(SimpleTestCase):
    def test_empty_output(self):
        result = inspect_llm_response_output_for_reasoning(type("R", (), {"output": []})())

        self.assertEqual(result["output_types"], [])
        self.assertEqual(result["reasoning_items"], 0)
        self.assertEqual(result["reasoning_with_summary"], 0)

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

    def test_dict_shaped_response(self):
        result = inspect_llm_response_output_for_reasoning(
            {"output": [{"type": "message"}, {"type": "reasoning", "summary": [{"text": "ok"}]}]}
        )

        self.assertEqual(result["reasoning_items"], 1)
        self.assertEqual(result["reasoning_with_summary"], 1)
