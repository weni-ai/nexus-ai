"""Explicit prompt caching for GPT-5.6 models served by AWS Mantle."""

import logging
from collections.abc import AsyncIterator
from dataclasses import replace
from threading import Lock
from typing import Literal

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
MANAGER_CACHE_PROFILE = "manager"
COLLABORATOR_CACHE_PROFILE = "collaborator"
CacheProfile = Literal["manager", "collaborator"]
MANAGER_PROMPT_CACHE_KEY = "cache_manager_2_8_luna_v1"
COLLABORATOR_PROMPT_CACHE_KEY = "cache_collaborator_2_8_luna_v1"
# Backwards-compatible alias for callers and tests that still use the original name.
PROMPT_CACHE_KEY_PREFIX = MANAGER_PROMPT_CACHE_KEY
PROMPT_CACHE_OPTIONS = {"mode": "explicit", "ttl": "30m"}
PROMPT_CACHE_BREAKPOINT = {"mode": "explicit"}
PROMPT_CACHE_MODELS = frozenset({"openai.gpt-5.6-luna"})


def supports_explicit_prompt_cache(model: str, model_vendor: str) -> bool:
    return (model_vendor or "").lower() == "aws_mantle" and model in PROMPT_CACHE_MODELS


_warned_models: set[tuple[str, CacheProfile]] = set()


def _log_missing_markers_once(model: str, cache_profile: CacheProfile) -> None:
    warning_key = (model, cache_profile)
    if warning_key in _warned_models:
        return
    _warned_models.add(warning_key)
    required_markers = (
        f"{OBJECTIVE_MARKER}, {SESSION_CONTEXT_MARKER}"
        if cache_profile == MANAGER_CACHE_PROFILE
        else OBJECTIVE_MARKER
    )
    logger.warning(
        "Explicit prompt caching disabled for %s %s because required markers are missing: %s",
        cache_profile,
        model,
        required_markers,
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


def split_collaborator_cacheable_instructions(instructions: str) -> tuple[str, str] | None:
    """Split collaborator instructions into shared guidelines and its playbook."""
    objective_index = instructions.find(OBJECTIVE_MARKER)
    if objective_index < 0:
        return None
    return instructions[:objective_index], instructions[objective_index:]


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

    return items, MANAGER_PROMPT_CACHE_KEY


def build_collaborator_cacheable_input(
    instructions: str,
    input_items: str | list[TResponseInputItem],
) -> tuple[list[TResponseInputItem], str] | None:
    """Move collaborator instructions to two explicitly cached developer sections."""
    sections = split_collaborator_cacheable_instructions(instructions)
    if sections is None:
        return None

    global_static, project_static = sections
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
        ],
    }

    if isinstance(input_items, str):
        items: list[TResponseInputItem] = [
            developer_message,
            {"role": "user", "content": input_items},
        ]
    else:
        items = [developer_message, *input_items]

    return items, COLLABORATOR_PROMPT_CACHE_KEY


def with_explicit_cache_settings(model_settings: ModelSettings, cache_key: str) -> ModelSettings:
    """Add cache settings while preserving all existing Nexus model settings."""
    extra_body = dict(model_settings.extra_body or {})
    extra_body.setdefault("prompt_cache_options", PROMPT_CACHE_OPTIONS)

    extra_args = dict(model_settings.extra_args or {})
    extra_args.setdefault("prompt_cache_key", cache_key)

    return replace(model_settings, extra_body=extra_body, extra_args=extra_args)


class PromptCachingOpenAIResponsesModel(Model):
    """Responses model that applies Manager 2.8 and collaborator prompt caching.

    The wrapped OpenAIResponsesModel is created on first use, not in __init__.
    Supervisor is built in the adapter before OpenAIBackend._set_openai_client()
    binds the process-wide Mantle client for this invocation.
    """

    def __init__(self, model: str, cache_profile: CacheProfile = MANAGER_CACHE_PROFILE):
        self.model = model
        self.cache_profile = cache_profile
        self._responses_model: OpenAIResponsesModel | None = None
        self._responses_model_lock = Lock()

    def _model(self) -> OpenAIResponsesModel:
        with self._responses_model_lock:
            if self._responses_model is None:
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

        if self.cache_profile == COLLABORATOR_CACHE_PROFILE:
            cacheable = build_collaborator_cacheable_input(system_instructions, input_items)
        else:
            cacheable = build_cacheable_input(system_instructions, input_items)
        if cacheable is None:
            _log_missing_markers_once(self.model, self.cache_profile)
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
