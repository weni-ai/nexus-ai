"""Explicit prompt caching for GPT-5.6 models served by AWS Mantle."""

import logging
from collections.abc import AsyncIterator
from dataclasses import replace
from functools import lru_cache

from agents import ModelSettings
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.items import TResponseInputItem, TResponseStreamEvent
from agents.models._openai_shared import get_default_openai_client
from agents.models.interface import Model, ModelResponse, ModelTracing
from agents.models.openai_responses import OpenAIResponsesModel
from agents.tool import Tool
from openai.types.responses.response_prompt_param import ResponsePromptParam

logger = logging.getLogger(__name__)

OBJECTIVE_MARKER = "<objective>"
SESSION_CONTEXT_MARKER = "<session_context>"
PROMPT_CACHE_KEY_PREFIX = "cache_manager_2_8_luna_v1"
PROMPT_CACHE_OPTIONS = {"mode": "explicit", "ttl": "30m"}
PROMPT_CACHE_BREAKPOINT = {"mode": "explicit"}
PROMPT_CACHE_MODELS = frozenset({"openai.gpt-5.6-luna"})


def supports_explicit_prompt_cache(model: str, model_vendor: str) -> bool:
    return (model_vendor or "").lower() == "aws_mantle" and model in PROMPT_CACHE_MODELS


@lru_cache(maxsize=None)
def _log_missing_markers_once(model: str) -> None:
    logger.warning(
        "Explicit prompt caching disabled for %s because Manager 2.8 markers are missing: %s, %s",
        model,
        OBJECTIVE_MARKER,
        SESSION_CONTEXT_MARKER,
    )


def split_cacheable_instructions(instructions: str) -> tuple[str, str, str] | None:
    """Split the Manager 2.8 prompt into global, project, and session sections."""
    objective_index = instructions.find(OBJECTIVE_MARKER)
    session_context_index = instructions.find(SESSION_CONTEXT_MARKER)

    if objective_index < 0 or session_context_index <= objective_index:
        return None

    return (
        instructions[:objective_index],
        instructions[objective_index:session_context_index],
        instructions[session_context_index:],
    )


def build_cacheable_input(
    instructions: str,
    input_items: str | list[TResponseInputItem],
) -> tuple[list[TResponseInputItem], str] | None:
    """Move system instructions to a developer message with explicit breakpoints."""
    sections = split_cacheable_instructions(instructions)
    if sections is None:
        return None

    global_static, project_static, session_context = sections
    developer_message: TResponseInputItem = {
        "type": "message",
        "role": "developer",
        "content": [
            {
                "type": "input_text",
                "text": global_static,
                "prompt_cache_breakpoint": PROMPT_CACHE_BREAKPOINT,
            },
            {
                "type": "input_text",
                "text": project_static,
                "prompt_cache_breakpoint": PROMPT_CACHE_BREAKPOINT,
            },
            {"type": "input_text", "text": session_context},
        ],
    }

    if isinstance(input_items, str):
        items: list[TResponseInputItem] = [
            developer_message,
            {"role": "user", "content": input_items},
        ]
    else:
        items = [developer_message, *input_items]

    return items, PROMPT_CACHE_KEY_PREFIX


def with_explicit_cache_settings(model_settings: ModelSettings, cache_key: str) -> ModelSettings:
    """Add cache settings while preserving all existing Nexus model settings."""
    extra_body = dict(model_settings.extra_body or {})
    extra_body.setdefault("prompt_cache_options", PROMPT_CACHE_OPTIONS)

    extra_args = dict(model_settings.extra_args or {})
    extra_args.setdefault("prompt_cache_key", cache_key)

    return replace(model_settings, extra_body=extra_body, extra_args=extra_args)


class PromptCachingOpenAIResponsesModel(Model):
    """Lazy Responses model that applies Manager 2.8 explicit prompt caching."""

    def __init__(self, model: str):
        self.model = model
        self._responses_model: OpenAIResponsesModel | None = None

    def _model(self) -> OpenAIResponsesModel:
        if self._responses_model is not None:
            return self._responses_model

        client = get_default_openai_client()
        if client is None:
            raise RuntimeError("The default OpenAI client must be configured before invoking AWS Mantle")
        self._responses_model = OpenAIResponsesModel(model=self.model, openai_client=client)
        return self._responses_model

    def _prepare(
        self,
        system_instructions: str | None,
        input_items: str | list[TResponseInputItem],
        model_settings: ModelSettings,
    ) -> tuple[str | None, str | list[TResponseInputItem], ModelSettings]:
        if not system_instructions:
            return system_instructions, input_items, model_settings

        cacheable = build_cacheable_input(system_instructions, input_items)
        if cacheable is None:
            _log_missing_markers_once(self.model)
            return system_instructions, input_items, model_settings

        cached_input, cache_key = cacheable
        return None, cached_input, with_explicit_cache_settings(model_settings, cache_key)

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
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        system_instructions, input, model_settings = self._prepare(
            system_instructions,
            input,
            model_settings,
        )
        return await self._model().get_response(
            system_instructions,
            input,
            model_settings,
            tools,
            output_schema,
            handoffs,
            tracing,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )

    async def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        system_instructions, input, model_settings = self._prepare(
            system_instructions,
            input,
            model_settings,
        )
        async for event in self._model().stream_response(
            system_instructions,
            input,
            model_settings,
            tools,
            output_schema,
            handoffs,
            tracing,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        ):
            yield event
