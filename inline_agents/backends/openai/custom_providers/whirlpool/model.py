"""Agents SDK Model implementation backed by Whirlpool generateContent."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Dict

from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.items import ModelResponse, TResponseInputItem, TResponseStreamEvent
from agents.model_settings import ModelSettings
from agents.models.chatcmpl_converter import Converter
from agents.models.interface import Model, ModelTracing
from agents.tool import Tool
from agents.tracing import generation_span
from agents.usage import Usage
from openai import omit
from openai.types.responses.response_prompt_param import ResponsePromptParam

from inline_agents.backends.openai.custom_providers.base import (
    chat_message_to_model_response,
    synthesize_stream_from_message,
)
from inline_agents.backends.openai.custom_providers.whirlpool.client import (
    WhirlpoolAPIError,
    WhirlpoolClient,
)
from inline_agents.backends.openai.custom_providers.whirlpool.translate import (
    WhirlpoolTranslationError,
    assert_tools_accepted,
    build_generate_content_payload,
    gemini_response_to_chat_message,
    openai_tool_names,
)

logger = logging.getLogger(__name__)


class WhirlpoolModel(Model):
    """In-process adapter: Agents SDK Model protocol → Whirlpool generateContent."""

    def __init__(self, model: str, credentials: Dict[str, Any] | None = None):
        self.model = model
        self.credentials = credentials or {}
        self._client = WhirlpoolClient(self.credentials)

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None = None,
        conversation_id: str | None = None,
        prompt: ResponsePromptParam | None = None,
    ) -> ModelResponse:
        with generation_span(
            model=str(self.model),
            model_config=model_settings.to_json_dict()
            | {"model_impl": "whirlpool", "base_url": self._client.generate_content_url},
            disabled=tracing.is_disabled(),
        ) as span_generation:
            message, usage = await self._complete(
                system_instructions=system_instructions,
                input=input,
                model_settings=model_settings,
                tools=tools,
                handoffs=handoffs,
                span_generation=span_generation,
                tracing=tracing,
            )
            if tracing.include_data():
                span_generation.span_data.output = [message.model_dump()]
            span_generation.span_data.usage = {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            }
            return chat_message_to_model_response(message, model=self.model, usage=usage)

    def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None = None,
        conversation_id: str | None = None,
        prompt: ResponsePromptParam | None = None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        return self._stream_response_impl(
            system_instructions,
            input,
            model_settings,
            tools,
            handoffs,
            tracing,
        )

    async def _stream_response_impl(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        handoffs: list[Handoff],
        tracing: ModelTracing,
    ) -> AsyncIterator[TResponseStreamEvent]:
        with generation_span(
            model=str(self.model),
            model_config=model_settings.to_json_dict()
            | {"model_impl": "whirlpool", "base_url": self._client.generate_content_url},
            disabled=tracing.is_disabled(),
        ) as span_generation:
            message, usage = await self._complete(
                system_instructions=system_instructions,
                input=input,
                model_settings=model_settings,
                tools=tools,
                handoffs=handoffs,
                span_generation=span_generation,
                tracing=tracing,
            )
            if tracing.include_data():
                span_generation.span_data.output = [message.model_dump()]
            span_generation.span_data.usage = {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            }
            async for event in synthesize_stream_from_message(
                message, model=self.model, model_settings=model_settings
            ):
                yield event

    async def _complete(
        self,
        *,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        handoffs: list[Handoff],
        span_generation,
        tracing: ModelTracing,
    ):
        messages = Converter.items_to_messages(
            input,
            preserve_thinking_blocks=False,
            preserve_tool_output_all_content=True,
            model=self.model,
        )
        if system_instructions:
            messages.insert(0, {"role": "system", "content": system_instructions})

        tool_choice = Converter.convert_tool_choice(model_settings.tool_choice)
        normalized_tool_choice = None if tool_choice is omit or tool_choice is None else tool_choice

        payload = build_generate_content_payload(
            messages=messages,
            tools=tools,
            handoffs=handoffs,
            max_tokens=model_settings.max_tokens,
            tool_choice=normalized_tool_choice,
        )

        if tracing.include_data():
            span_generation.span_data.input = messages

        requested = openai_tool_names(tools, handoffs)
        logger.debug(
            "WhirlpoolModel calling generateContent model=%s tools=%s payload_keys=%s",
            self.model,
            requested,
            list(payload.keys()),
        )

        try:
            response = await self._client.generate_content(payload)
        except WhirlpoolAPIError as exc:
            body_str = str(exc.body) if exc.body is not None else ""
            if requested and any(
                token in body_str.lower() for token in ("tool", "function", "unsupported")
            ):
                raise WhirlpoolTranslationError(
                    "Whirlpool rejected tool/function calling required by inline agents. "
                    f"Requested tools={requested}. Status={exc.status_code}. Body={exc.body!r}"
                ) from exc
            raise

        assert_tools_accepted(
            requested_tool_names=requested,
            request_payload=payload,
            response=response,
        )

        try:
            message = gemini_response_to_chat_message(response)
        except WhirlpoolTranslationError:
            logger.error(
                "Whirlpool response translation failed. Response preview: %s",
                json.dumps(response, ensure_ascii=False)[:2000],
            )
            raise

        usage = _usage_from_gemini(response)
        return message, usage


def _usage_from_gemini(response: Dict[str, Any]) -> Usage:
    meta = response.get("usageMetadata") or response.get("usage") or {}
    if not isinstance(meta, dict):
        return Usage()
    prompt = int(meta.get("promptTokenCount") or meta.get("prompt_tokens") or 0)
    completion = int(meta.get("candidatesTokenCount") or meta.get("completion_tokens") or 0)
    total = int(meta.get("totalTokenCount") or meta.get("total_tokens") or (prompt + completion))
    if prompt or completion or total:
        return Usage(requests=1, input_tokens=prompt, output_tokens=completion, total_tokens=total)
    return Usage()
