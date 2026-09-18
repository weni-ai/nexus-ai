import asyncio
import base64
import json

from agents.model_settings import ModelSettings
from agents.models.chatcmpl_converter import Converter
from agents.tool import FunctionTool
from django.test import SimpleTestCase, override_settings

from inline_agents.backends.openai.custom_providers.base import (
    chat_message_to_model_response,
    synthesize_stream_from_message,
)
from inline_agents.backends.openai.custom_providers.whirlpool.model import SDK_GEMINI_MODEL_HINT
from inline_agents.backends.openai.custom_providers.whirlpool.translate import (
    _TOOL_RESULT_CONTINUATION_TEXT,
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


WHIRLPOOL_MODEL = "custom/whirlpool/generateContent"


def _function_call_response(signature="synthetic-signature"):
    return {
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
                            "thoughtSignature": signature,
                        }
                    ],
                }
            }
        ]
    }


def _next_turn_contents(output_items):
    """Replay SDK history into the payload WhirlpoolModel sends on the next turn."""
    items = [item.model_dump() for item in output_items]
    call_id = next(item["call_id"] for item in items if item["type"] == "function_call")
    history = [
        {"role": "user", "content": "Find products"},
        *items,
        {"type": "function_call_output", "call_id": call_id, "output": '{"products":[]}'},
    ]
    messages = Converter.items_to_messages(
        history,
        preserve_thinking_blocks=False,
        preserve_tool_output_all_content=True,
        model=SDK_GEMINI_MODEL_HINT,
    )
    _, contents = chat_messages_to_gemini_contents(messages)
    return contents


async def _streamed_output_items(message):
    outputs = []
    async for event in synthesize_stream_from_message(
        message,
        model=WHIRLPOOL_MODEL,
        model_settings=ModelSettings(),
        converter_model=SDK_GEMINI_MODEL_HINT,
    ):
        if event.type == "response.completed":
            outputs = list(event.response.output)
    return outputs


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

    def test_unsigned_function_call_gets_validation_skip_sentinel(self):
        """Context injected as a tool result is a call Gemini never generated."""
        _, contents = chat_messages_to_gemini_contents(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_ctx_1",
                            "type": "function",
                            "function": {"name": "get_context", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call_ctx_1", "content": "cart: empty"},
                {"role": "user", "content": "Where is my order?"},
            ]
        )
        signature = contents[0]["parts"][0]["thoughtSignature"]
        self.assertEqual(base64.b64decode(signature), b"skip_thought_signature_validator")

    def test_parallel_tool_results_share_one_user_turn(self):
        """Gemini 400s on interleaved calls/responses: all FCs, then all FRs."""
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
                            "function": {"name": "searchproducts", "arguments": "{}"},
                        },
                        {
                            "id": "call_2",
                            "type": "function",
                            "function": {"name": "getproductdetails", "arguments": "{}"},
                        },
                    ],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": '{"products":[]}'},
                {"role": "tool", "tool_call_id": "call_2", "content": '{"details":{}}'},
            ]
        )
        self.assertEqual(len(contents), 3)
        self.assertEqual(
            [part["functionCall"]["name"] for part in contents[1]["parts"]],
            ["searchproducts", "getproductdetails"],
        )
        self.assertEqual(
            [
                part["functionResponse"]["name"]
                for part in contents[2]["parts"]
                if "functionResponse" in part
            ],
            ["searchproducts", "getproductdetails"],
        )

    def test_trailing_assistant_message_gets_a_closing_user_turn(self):
        """Gemini 400s with "Requests ending with a model turn are not supported"."""
        _, contents = chat_messages_to_gemini_contents(
            [
                {"role": "user", "content": "quero comprar uma geladeira"},
                {"role": "assistant", "content": "Vou verificar os modelos disponíveis."},
            ]
        )
        self.assertEqual([content["role"] for content in contents], ["user", "model", "user"])
        self.assertEqual(contents[-1]["parts"][0]["text"], _TOOL_RESULT_CONTINUATION_TEXT)

    def test_replayed_tool_call_without_result_gets_a_closing_user_turn(self):
        _, contents = chat_messages_to_gemini_contents(
            [
                {"role": "user", "content": "Where is my order?"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "lookup_order", "arguments": "{}"},
                        }
                    ],
                },
            ]
        )
        self.assertEqual(contents[-1]["role"], "user")

    def test_tool_result_turn_is_not_duplicated(self):
        _, contents = chat_messages_to_gemini_contents(
            [
                {"role": "user", "content": "Where is my order?"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "lookup_order", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call_1", "content": '{"status":"shipped"}'},
            ]
        )
        self.assertEqual([content["role"] for content in contents], ["user", "model", "user"])

    def test_agents_sdk_roundtrip_keeps_thought_signature_on_next_payload(self):
        message = gemini_response_to_chat_message(_function_call_response())
        response = chat_message_to_model_response(message, model=WHIRLPOOL_MODEL)

        contents = _next_turn_contents(response.output)

        self.assertEqual(contents[1]["parts"][0]["thoughtSignature"], "synthetic-signature")
        self.assertNotIn("thoughtSignature", json.dumps(contents[0]))

    def test_streamed_roundtrip_keeps_thought_signature_on_next_payload(self):
        """Inline agents run through ``run_streamed``, which synthesizes stream events."""
        message = gemini_response_to_chat_message(_function_call_response())
        outputs = asyncio.run(_streamed_output_items(message))

        contents = _next_turn_contents(outputs)

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
