import json

from agents.tool import FunctionTool
from django.test import SimpleTestCase

from inline_agents.backends.openai.custom_providers.whirlpool.translate import (
    WhirlpoolTranslationError,
    agents_tools_to_gemini,
    assert_tools_accepted,
    build_generate_content_payload,
    chat_messages_to_gemini_contents,
    gemini_response_to_chat_message,
)


def _dummy_tool(name="lookup_order"):
    async def _on_invoke(ctx, raw):
        return "{}"

    return FunctionTool(
        name=name,
        description="Lookup an order",
        params_json_schema={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
        on_invoke_tool=_on_invoke,
    )


class WhirlpoolTranslateTests(SimpleTestCase):
    def test_chat_messages_to_gemini_system_and_user(self):
        system, contents = chat_messages_to_gemini_contents(
            [
                {"role": "system", "content": "Be helpful"},
                {"role": "user", "content": "Hello"},
            ]
        )
        self.assertEqual(system["parts"][0]["text"], "Be helpful")
        self.assertEqual(contents[0]["role"], "user")
        self.assertEqual(contents[0]["parts"][0]["text"], "Hello")

    def test_assistant_tool_calls_and_tool_results(self):
        system, contents = chat_messages_to_gemini_contents(
            [
                {"role": "user", "content": "hi"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "lookup_order", "arguments": '{"order_id":"1"}'},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "name": "lookup_order",
                    "content": '{"status":"ok"}',
                },
            ]
        )
        self.assertIsNone(system)
        self.assertEqual(contents[1]["role"], "model")
        self.assertIn("functionCall", contents[1]["parts"][0])
        self.assertEqual(contents[2]["parts"][0]["functionResponse"]["name"], "lookup_order")

    def test_agents_tools_to_gemini_declarations(self):
        decls = agents_tools_to_gemini([_dummy_tool()])
        self.assertEqual(len(decls), 1)
        self.assertEqual(decls[0]["name"], "lookup_order")
        self.assertIn("parameters", decls[0])

    def test_build_payload_includes_tools_and_required_mode(self):
        payload = build_generate_content_payload(
            messages=[{"role": "user", "content": "hi"}],
            tools=[_dummy_tool()],
            tool_choice="required",
            max_tokens=128,
        )
        self.assertIn("tools", payload)
        self.assertEqual(payload["toolConfig"]["functionCallingConfig"]["mode"], "ANY")
        self.assertEqual(payload["generationConfig"]["maxOutputTokens"], 128)

    def test_gemini_response_text(self):
        message = gemini_response_to_chat_message(
            {
                "candidates": [
                    {"content": {"role": "model", "parts": [{"text": "Hello there"}]}}
                ]
            }
        )
        self.assertEqual(message.role, "assistant")
        self.assertEqual(message.content, "Hello there")
        self.assertIsNone(message.tool_calls)

    def test_gemini_response_function_call(self):
        message = gemini_response_to_chat_message(
            {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": "lookup_order",
                                        "args": {"order_id": "99"},
                                    }
                                }
                            ],
                        }
                    }
                ]
            }
        )
        self.assertEqual(len(message.tool_calls), 1)
        self.assertEqual(message.tool_calls[0].function.name, "lookup_order")
        self.assertEqual(json.loads(message.tool_calls[0].function.arguments)["order_id"], "99")

    def test_assert_tools_accepted_raises_on_tool_error(self):
        with self.assertRaises(WhirlpoolTranslationError):
            assert_tools_accepted(
                requested_tool_names=["lookup_order"],
                request_payload={"tools": []},
                response={"error": {"message": "Function calling unsupported"}},
            )

    def test_assert_tools_accepted_ok_without_error(self):
        assert_tools_accepted(
            requested_tool_names=["lookup_order"],
            request_payload={"tools": [{}]},
            response={"candidates": []},
        )
