import asyncio
from unittest.mock import AsyncMock, patch

from agents.model_settings import ModelSettings
from agents.models.interface import ModelTracing
from agents.tool import FunctionTool
from django.test import SimpleTestCase, override_settings

from inline_agents.backends.openai.custom_providers.whirlpool.client import (
    WhirlpoolAPIError,
    clear_token_cache,
)
from inline_agents.backends.openai.custom_providers.whirlpool.model import WhirlpoolModel
from inline_agents.backends.openai.custom_providers.whirlpool.translate import (
    WhirlpoolTranslationError,
)


GUARD_MESSAGE = "I'm sorry, I can't help with that request."


class WhirlpoolModelTests(SimpleTestCase):
    def setUp(self):
        clear_token_cache()
        self.model = WhirlpoolModel(
            model="custom/whirlpool/generateContent",
            credentials={"client_id": "cid", "client_secret": "csecret"},
        )

    def test_get_response_text(self):
        async def _run():
            with patch(
                "inline_agents.backends.openai.custom_providers.whirlpool.client.WhirlpoolClient.generate_content",
                new_callable=AsyncMock,
            ) as mock_generate:
                mock_generate.return_value = {
                    "candidates": [{"content": {"parts": [{"text": "Oi"}]}}],
                    "usageMetadata": {
                        "promptTokenCount": 3,
                        "candidatesTokenCount": 1,
                        "totalTokenCount": 4,
                    },
                }
                response = await self.model.get_response(
                    system_instructions="sys",
                    input="hello",
                    model_settings=ModelSettings(),
                    tools=[],
                    output_schema=None,
                    handoffs=[],
                    tracing=ModelTracing.DISABLED,
                )
                self.assertTrue(response.output)
                mock_generate.assert_awaited_once()
                payload = mock_generate.await_args.args[0]
                self.assertIn("contents", payload)
                self.assertIn("systemInstruction", payload)

        asyncio.run(_run())

    def test_tools_rejection_raises(self):
        async def _on_invoke(ctx, raw):
            return "{}"

        tool = FunctionTool(
            name="lookup_order",
            description="Lookup",
            params_json_schema={"type": "object", "properties": {}},
            on_invoke_tool=_on_invoke,
        )

        async def _run():
            with patch(
                "inline_agents.backends.openai.custom_providers.whirlpool.client.WhirlpoolClient.generate_content",
                new_callable=AsyncMock,
            ) as mock_generate:
                mock_generate.side_effect = WhirlpoolAPIError(
                    "bad",
                    status_code=400,
                    body={"error": {"message": "function calling unsupported"}},
                )
                with self.assertRaises(WhirlpoolTranslationError):
                    await self.model.get_response(
                        system_instructions=None,
                        input="hello",
                        model_settings=ModelSettings(tool_choice="required"),
                        tools=[tool],
                        output_schema=None,
                        handoffs=[],
                        tracing=ModelTracing.DISABLED,
                    )

        asyncio.run(_run())

    @override_settings(WHIRLPOOL_GUARD_BLOCK_MESSAGES=[GUARD_MESSAGE])
    def test_guard_block_400_becomes_assistant_reply(self):
        async def _run():
            with patch(
                "inline_agents.backends.openai.custom_providers.whirlpool.client.WhirlpoolClient.generate_content",
                new_callable=AsyncMock,
            ) as mock_generate:
                mock_generate.side_effect = WhirlpoolAPIError(
                    "blocked",
                    status_code=400,
                    body={"error_code": "400-001", "error_description": GUARD_MESSAGE},
                )
                response = await self.model.get_response(
                    system_instructions=None,
                    input="hello",
                    model_settings=ModelSettings(),
                    tools=[],
                    output_schema=None,
                    handoffs=[],
                    tracing=ModelTracing.DISABLED,
                )
                texts = [
                    content.text
                    for item in response.output
                    for content in getattr(item, "content", []) or []
                    if getattr(content, "text", None)
                ]
                self.assertIn(GUARD_MESSAGE, texts)

        asyncio.run(_run())

    @override_settings(WHIRLPOOL_GUARD_BLOCK_MESSAGES=[GUARD_MESSAGE])
    def test_other_400_still_raises(self):
        async def _run():
            with patch(
                "inline_agents.backends.openai.custom_providers.whirlpool.client.WhirlpoolClient.generate_content",
                new_callable=AsyncMock,
            ) as mock_generate:
                mock_generate.side_effect = WhirlpoolAPIError(
                    "bad request",
                    status_code=400,
                    body={"error_code": "400-001", "error_description": "Bad Request"},
                )
                with self.assertRaises(WhirlpoolAPIError):
                    await self.model.get_response(
                        system_instructions=None,
                        input="hello",
                        model_settings=ModelSettings(),
                        tools=[],
                        output_schema=None,
                        handoffs=[],
                        tracing=ModelTracing.DISABLED,
                    )

        asyncio.run(_run())

    def test_stream_response_synthesizes_events(self):
        async def _run():
            with patch(
                "inline_agents.backends.openai.custom_providers.whirlpool.client.WhirlpoolClient.generate_content",
                new_callable=AsyncMock,
            ) as mock_generate:
                mock_generate.return_value = {
                    "candidates": [{"content": {"parts": [{"text": "streamed"}]}}],
                }
                events = []
                async for event in self.model.stream_response(
                    system_instructions=None,
                    input="hello",
                    model_settings=ModelSettings(),
                    tools=[],
                    output_schema=None,
                    handoffs=[],
                    tracing=ModelTracing.DISABLED,
                ):
                    events.append(event)
                self.assertTrue(events)
                types = {getattr(e, "type", None) for e in events}
                self.assertIn("response.created", types)

        asyncio.run(_run())
