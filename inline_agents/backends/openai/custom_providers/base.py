"""Shared helpers for custom Model providers."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any, Optional

from agents.items import ModelResponse, TResponseStreamEvent
from agents.models.chatcmpl_converter import Converter
from agents.models.chatcmpl_stream_handler import ChatCmplStreamHandler
from agents.models.fake_id import FAKE_RESPONSES_ID
from agents.model_settings import ModelSettings
from agents.usage import Usage
from openai.types.chat import ChatCompletionChunk, ChatCompletionMessage
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
from openai.types.chat.chat_completion_chunk import ChoiceDelta
from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall
from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCallFunction
from openai.types.responses import Response
from openai.types.shared import Reasoning


def chat_message_to_model_response(
    message: ChatCompletionMessage,
    *,
    model: str,
    usage: Optional[Usage] = None,
) -> ModelResponse:
    """Convert an OpenAI ChatCompletionMessage into Agents ModelResponse."""
    provider_data = {"model": model}
    items = Converter.message_to_output_items(message, provider_data=provider_data)
    return ModelResponse(
        output=items,
        usage=usage or Usage(),
        response_id=None,
    )


def _tool_calls_as_delta(message: ChatCompletionMessage) -> list[ChoiceDeltaToolCall] | None:
    if not message.tool_calls:
        return None
    deltas: list[ChoiceDeltaToolCall] = []
    for i, tc in enumerate(message.tool_calls):
        fn = getattr(tc, "function", None)
        deltas.append(
            ChoiceDeltaToolCall(
                index=i,
                id=getattr(tc, "id", None) or f"call_{i}",
                type="function",
                function=ChoiceDeltaToolCallFunction(
                    name=getattr(fn, "name", None) if fn else None,
                    arguments=getattr(fn, "arguments", None) if fn else None,
                ),
            )
        )
    return deltas


async def synthesize_stream_from_message(
    message: ChatCompletionMessage,
    *,
    model: str,
    model_settings: ModelSettings,
) -> AsyncIterator[TResponseStreamEvent]:
    """Emit Agents stream events from a complete chat message (non-streaming APIs)."""
    parallel = bool(model_settings.parallel_tool_calls) if model_settings.parallel_tool_calls else False
    tool_choice: Any = "auto"
    if model_settings.tool_choice is not None:
        tool_choice = model_settings.tool_choice

    response = Response(
        id=FAKE_RESPONSES_ID,
        created_at=time.time(),
        model=model,
        object="response",
        output=[],
        tool_choice=tool_choice,
        top_p=model_settings.top_p,
        temperature=model_settings.temperature,
        tools=[],
        parallel_tool_calls=parallel,
        reasoning=model_settings.reasoning if isinstance(model_settings.reasoning, Reasoning) else None,
    )

    delta = ChoiceDelta(
        role="assistant",
        content=message.content,
        tool_calls=_tool_calls_as_delta(message),
    )
    chunk = ChatCompletionChunk(
        id=FAKE_RESPONSES_ID,
        choices=[
            ChunkChoice(
                index=0,
                delta=delta,
                finish_reason="tool_calls" if message.tool_calls else "stop",
            )
        ],
        created=int(time.time()),
        model=model,
        object="chat.completion.chunk",
    )

    async def _single_chunk_stream():
        yield chunk

    async for event in ChatCmplStreamHandler.handle_stream(response, _single_chunk_stream(), model=model):
        yield event
