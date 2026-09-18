import json

from agents.models.chatcmpl_converter import Converter
from agents.tool import FunctionTool
from django.test import SimpleTestCase, override_settings

from inline_agents.backends.openai.custom_providers.base import chat_message_to_model_response
from inline_agents.backends.openai.custom_providers.whirlpool.translate import (
    WhirlpoolTranslationError,
    agents_tools_to_gemini,
    assert_tools_accepted,
    build_generate_content_payload,
    chat_messages_to_gemini_contents,
    gemini_response_to_chat_message,
    guard_block_message,
    sanitize_json_schema_for_gemini,
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
                    "content": '{"status":"ok"}',
                },
            ]
        )
        self.assertIsNone(system)
        self.assertEqual(contents[1]["role"], "model")
        self.assertIn("functionCall", contents[1]["parts"][0])
        self.assertEqual(contents[2]["parts"][0]["functionResponse"]["name"], "lookup_order")
        self.assertEqual(contents[2]["parts"][-1], {"text": "Continue using the tool result above."})

    def test_plain_user_turn_remains_the_last_prompt_text(self):
        _, contents = chat_messages_to_gemini_contents(
            [{"role": "user", "content": "Where is my order?"}]
        )
        self.assertEqual(contents, [{"role": "user", "parts": [{"text": "Where is my order?"}]}])

    def test_build_payload_keeps_tool_response_and_gateway_prompt(self):
        payload = build_generate_content_payload(
            messages=[
                {"role": "user", "content": "Find products"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "searchproducts", "arguments": '{"query":"washer"}'},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "content": '{"products":[{"id":"1"}]}',
                },
            ],
            tools=[_dummy_tool("searchproducts")],
        )

        final_parts = payload["contents"][-1]["parts"]
        self.assertEqual(final_parts[0]["functionResponse"]["name"], "searchproducts")
        self.assertEqual(
            final_parts[0]["functionResponse"]["response"],
            {"products": [{"id": "1"}]},
        )
        self.assertEqual(final_parts[-1], {"text": "Continue using the tool result above."})
        self.assertTrue(final_parts[-1]["text"].strip())

    def test_agents_tools_to_gemini_declarations(self):
        decls = agents_tools_to_gemini([_dummy_tool()])
        self.assertEqual(len(decls), 1)
        self.assertEqual(decls[0]["name"], "lookup_order")
        self.assertIn("parameters", decls[0])

    def test_sanitizes_optional_array_anyof_siblings_for_gemini(self):
        async def _on_invoke(ctx, raw):
            return "{}"

        tool = FunctionTool(
            name="sendcatalog",
            description="Send catalog",
            params_json_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "more_options_text": {
                        "anyOf": [
                            {"items": {"type": "string"}, "type": "array"},
                            {"type": "null"},
                        ],
                        "default": None,
                        "description": "optional labels",
                        "title": "More Options Text",
                        "type": "array",
                    }
                },
            },
            on_invoke_tool=_on_invoke,
        )
        param = agents_tools_to_gemini([tool])[0]["parameters"]["properties"]["more_options_text"]
        self.assertNotIn("anyOf", param)
        self.assertNotIn("title", param)
        self.assertNotIn("default", param)
        self.assertEqual(param["type"], "array")
        self.assertTrue(param["nullable"])
        self.assertEqual(param["items"], {"type": "string"})
        self.assertNotIn("additionalProperties", agents_tools_to_gemini([tool])[0]["parameters"])

    def test_sanitize_optional_scalar_and_keeps_true_unions(self):
        scalar = sanitize_json_schema_for_gemini(
            {"anyOf": [{"type": "string"}, {"type": "null"}], "title": "X", "type": "string"}
        )
        self.assertEqual(scalar, {"type": "string", "nullable": True})

        union = sanitize_json_schema_for_gemini(
            {
                "anyOf": [{"type": "string"}, {"type": "integer"}],
                "description": "either",
                "title": "Y",
            }
        )
        self.assertEqual(union, {"anyOf": [{"type": "string"}, {"type": "integer"}]})

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
        self.assertIsNone(getattr(message.tool_calls[0], "extra_content", None))

    def test_replays_function_call_thought_signature(self):
        message = gemini_response_to_chat_message(
            {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": "searchproducts",
                                        "args": {"query": "washer"},
                                    },
                                    "thoughtSignature": "synthetic-signature",
                                }
                            ],
                        }
                    }
                ]
            }
        )
        self.assertEqual(
            message.tool_calls[0].extra_content,
            {"google": {"thought_signature": "synthetic-signature"}},
        )

        _, contents = chat_messages_to_gemini_contents(
            [
                {"role": "user", "content": "Find products"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "searchproducts",
                                "arguments": '{"query":"washer"}',
                            },
                            "extra_content": {
                                "google": {"thought_signature": "synthetic-signature"}
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "content": '{"products":[]}',
                },
            ]
        )
        function_call_part = contents[1]["parts"][0]
        self.assertEqual(function_call_part["functionCall"]["name"], "searchproducts")
        self.assertEqual(function_call_part["thoughtSignature"], "synthetic-signature")

    def test_attaches_sibling_thought_signature_to_first_function_call_only(self):
        message = gemini_response_to_chat_message(
            {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "thought": True,
                                    "text": "internal",
                                    "thoughtSignature": "synthetic-turn-signature",
                                },
                                {
                                    "functionCall": {
                                        "name": "searchproducts",
                                        "args": {"query": "washer"},
                                    }
                                },
                                {
                                    "functionCall": {
                                        "name": "getproductdetails",
                                        "args": {"id": "1"},
                                    }
                                },
                            ],
                        }
                    }
                ]
            }
        )
        self.assertIsNone(message.content)
        self.assertEqual(
            message.tool_calls[0].extra_content["google"]["thought_signature"],
            "synthetic-turn-signature",
        )
        self.assertIsNone(message.tool_calls[1].extra_content)

    def test_agents_sdk_roundtrip_keeps_thought_signature_on_next_payload(self):
        message = gemini_response_to_chat_message(
            {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [
                                {
                                    "functionCall": {
                                        "name": "searchproducts",
                                        "args": {"query": "washer"},
                                    },
                                    "thoughtSignature": "synthetic-signature",
                                }
                            ],
                        }
                    }
                ]
            }
        )
        items = [
            item.model_dump()
            for item in chat_message_to_model_response(
                message, model="custom/whirlpool/generateContent"
            ).output
        ]
        items.append(
            {
                "type": "function_call_output",
                "call_id": items[0]["call_id"],
                "output": '{"products":[]}',
            }
        )
        history = [
            {"role": "user", "content": "Find products"},
            *items,
        ]
        messages = Converter.items_to_messages(
            history,
            preserve_thinking_blocks=False,
            preserve_tool_output_all_content=True,
            model="gemini",
        )
        _, contents = chat_messages_to_gemini_contents(messages)
        self.assertEqual(contents[1]["parts"][0]["thoughtSignature"], "synthetic-signature")
        self.assertNotIn("thoughtSignature", json.dumps(contents[0]))

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


GUARD_MESSAGE = "I'm sorry, I can't help with that request."


@override_settings(WHIRLPOOL_GUARD_BLOCK_MESSAGES=[GUARD_MESSAGE])
class WhirlpoolGuardBlockTests(SimpleTestCase):
    def test_matches_configured_message_in_error_description(self):
        body = {"error_code": "400-001", "error_description": GUARD_MESSAGE}
        self.assertEqual(guard_block_message(400, body), GUARD_MESSAGE)

    def test_matches_nested_error_message(self):
        body = {"error": {"message": GUARD_MESSAGE}}
        self.assertEqual(guard_block_message(400, body), GUARD_MESSAGE)

    def test_ignores_other_400_bodies(self):
        body = {"error_code": "400-001", "error_description": "Bad Request"}
        self.assertIsNone(guard_block_message(400, body))

    def test_ignores_other_status_codes(self):
        body = {"error_description": GUARD_MESSAGE}
        self.assertIsNone(guard_block_message(500, body))

    @override_settings(WHIRLPOOL_GUARD_BLOCK_MESSAGES=[])
    def test_no_configured_messages_means_no_match(self):
        body = {"error_description": GUARD_MESSAGE}
        self.assertIsNone(guard_block_message(400, body))
