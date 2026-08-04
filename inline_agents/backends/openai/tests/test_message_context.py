"""Tests for message context extraction, session injection, and trace emission."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from inline_agents.backends.openai.message_context import (
    DEFAULT_CONTEXT_TOOL_NAME,
    emit_context_tool_traces,
    extract_message_context,
    inject_context_as_tool_result,
)

COFFEE_CONTEXT = """Product: Café Torrado e Moído Café da Condessa Pacote 500 g
Brand: Café da Condessa
Product ID: 9974
SKU ID: 9975
Description: Café Torrado e Moído 100% Arábica Café da Condessa Pacote 500g
Attributes: Características: moído | Tabela Nutricional: café

Selected SKU:

SKU 9975: Café Torrado e Moído Café da Condessa Pacote 500 g (activeSubscriptions: mensal) | Price: 49 | Available"""


class ExtractMessageContextTestCase(unittest.TestCase):
    def test_no_context_returns_original_text(self):
        text = "O café é 100% Arábica?"
        clean, context = extract_message_context(text)
        self.assertEqual(clean, text)
        self.assertIsNone(context)

    def test_extracts_multiline_context(self):
        text = f"O café é 100% Arábica?; Context: {COFFEE_CONTEXT}"
        clean, context = extract_message_context(text)
        self.assertEqual(clean, "O café é 100% Arábica?")
        self.assertEqual(context, COFFEE_CONTEXT)

    def test_strips_whitespace(self):
        text = "  Hello world  ; Context:  some context  "
        clean, context = extract_message_context(text)
        self.assertEqual(clean, "Hello world")
        self.assertEqual(context, "some context")

    def test_empty_context_after_delimiter_returns_none(self):
        text = "Hello; Context:   "
        clean, context = extract_message_context(text)
        self.assertEqual(clean, "Hello")
        self.assertIsNone(context)

    def test_empty_text(self):
        self.assertEqual(extract_message_context(""), ("", None))


class InjectContextAsToolResultTestCase(unittest.TestCase):
    def test_adds_paired_function_call_and_output(self):
        session = MagicMock()
        session.add_items = AsyncMock()

        asyncio.run(inject_context_as_tool_result(session, COFFEE_CONTEXT))

        session.add_items.assert_awaited_once()
        items = session.add_items.await_args.args[0]
        self.assertEqual(len(items), 2)

        function_call, function_output = items
        self.assertEqual(function_call["type"], "function_call")
        self.assertEqual(function_call["name"], DEFAULT_CONTEXT_TOOL_NAME)
        self.assertEqual(function_call["arguments"], "{}")
        self.assertEqual(function_output["type"], "function_call_output")
        self.assertEqual(function_output["output"], COFFEE_CONTEXT)
        self.assertEqual(function_call["call_id"], function_output["call_id"])
        self.assertTrue(function_call["call_id"].startswith("call_ctx_"))


class EmitContextToolTracesTestCase(unittest.TestCase):
    def test_sends_executing_tool_and_tool_result_received(self):
        trace_handler = MagicMock()
        trace_handler.send_trace = AsyncMock()
        context_data = MagicMock()
        context_data.session.get_session_id.return_value = "session-123"

        asyncio.run(emit_context_tool_traces(trace_handler, context_data, COFFEE_CONTEXT))

        self.assertEqual(trace_handler.send_trace.await_count, 2)

        first_call = trace_handler.send_trace.await_args_list[0]
        second_call = trace_handler.send_trace.await_args_list[1]

        self.assertEqual(first_call.args[1], "manager")
        self.assertEqual(first_call.args[2], "executing_tool")
        self.assertEqual(first_call.kwargs["tool_name"], DEFAULT_CONTEXT_TOOL_NAME)
        executing_payload = first_call.args[3]
        self.assertEqual(
            executing_payload["trace"]["orchestrationTrace"]["invocationInput"]["actionGroupInvocationInput"][
                "function"
            ],
            DEFAULT_CONTEXT_TOOL_NAME,
        )
        self.assertEqual(executing_payload["sessionId"], "session-123")

        self.assertEqual(second_call.args[2], "tool_result_received")
        self.assertEqual(second_call.kwargs["tool_name"], DEFAULT_CONTEXT_TOOL_NAME)
        result_payload = second_call.args[3]
        observation = result_payload["trace"]["orchestrationTrace"]["observation"]["actionGroupInvocationOutput"]
        self.assertEqual(observation["text"], COFFEE_CONTEXT)
        self.assertEqual(observation["tool_name"], DEFAULT_CONTEXT_TOOL_NAME)


if __name__ == "__main__":
    unittest.main()
