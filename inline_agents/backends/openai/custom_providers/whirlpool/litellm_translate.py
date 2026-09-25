"""LiteLLM Gemini request/response transforms for Whirlpool generateContent.

LiteLLM never becomes the HTTP client. ``WhirlpoolClient`` still POSTs the
translated body. After LiteLLM builds ``contents``, the Whirlpool gateway
last-turn prompt is applied here (not before LiteLLM, so openai-agents keeps
thought signatures on tool calls after the last user message).
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx
import litellm
from agents.handoffs import Handoff
from agents.models.chatcmpl_converter import Converter
from agents.tool import Tool
from django.conf import settings
from litellm.llms.vertex_ai.gemini.transformation import _transform_request_body
from litellm.llms.vertex_ai.gemini.vertex_and_google_ai_studio_gemini import (
    VertexGeminiConfig,
)
from litellm.types.utils import ModelResponse
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageParam
from openai.types.chat.chat_completion_message_function_tool_call import Function

from inline_agents.backends.openai.custom_providers.whirlpool.translate import (
    _SKIP_SIGNATURE_VALIDATION,
    _ToolCallWithThoughtSignature,
    _ensure_gateway_prompt_after_tool_result,
    _ensure_request_ends_with_user_turn,
    _thought_signature_from_tool_call,
    sanitize_json_schema_for_gemini,
    WhirlpoolTranslationError,
)

logger = logging.getLogger(__name__)

litellm.telemetry = False
litellm.suppress_debug_info = True

_CUSTOM_LLM_PROVIDER = "vertex_ai"

_GEMINI_KEY_ALIASES = {
    "system_instruction": "systemInstruction",
    "function_declarations": "functionDeclarations",
    "function_call": "functionCall",
    "function_response": "functionResponse",
    "thought_signature": "thoughtSignature",
    "max_output_tokens": "maxOutputTokens",
    "allowed_function_names": "allowedFunctionNames",
    "function_calling_config": "functionCallingConfig",
}


def _gemini_model_id() -> str:
    return getattr(settings, "WHIRLPOOL_GEMINI_MODEL", None) or "gemini-2.5-flash"


def chat_messages_to_gemini_contents(
    messages: Sequence[ChatCompletionMessageParam],
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    payload = build_generate_content_payload(messages=messages)
    return payload.get("systemInstruction"), payload.get("contents") or []


def build_generate_content_payload(
    *,
    messages: Sequence[ChatCompletionMessageParam],
    tools: Sequence[Tool] | None = None,
    handoffs: Sequence[Handoff] | None = None,
    max_tokens: int | None = None,
    tool_choice: Any = None,
) -> Dict[str, Any]:
    model = _gemini_model_id()
    openai_messages = _messages_for_litellm(messages)
    non_default: Dict[str, Any] = {}
    openai_tools = _agents_tools_to_openai(tools, handoffs)
    if openai_tools:
        non_default["tools"] = openai_tools
    if tool_choice is not None:
        non_default["tool_choice"] = tool_choice
    if max_tokens is not None:
        non_default["max_tokens"] = max_tokens

    try:
        optional_params = VertexGeminiConfig().map_openai_params(
            non_default_params=deepcopy(non_default),
            optional_params={},
            model=model,
            drop_params=True,
        )
        body = _transform_request_body(
            messages=openai_messages,
            model=model,
            optional_params=optional_params,
            custom_llm_provider=_CUSTOM_LLM_PROVIDER,
            litellm_params={},
            cached_content=None,
        )
    except WhirlpoolTranslationError:
        raise
    except Exception as exc:
        raise WhirlpoolTranslationError(
            f"LiteLLM Gemini request transform failed: {exc}"
        ) from exc

    payload = _camelize_gemini_payload(_to_plain(body))
    _sanitize_payload_tool_schemas(payload)

    contents = payload.get("contents")
    if not isinstance(contents, list):
        contents = []
        payload["contents"] = contents
    _ensure_content_roles(contents)

    _ensure_gateway_prompt_after_tool_result(contents)
    _ensure_request_ends_with_user_turn(contents)
    return payload


def gemini_response_to_chat_message(response: Dict[str, Any]) -> ChatCompletionMessage:
    candidates = response.get("candidates") or []
    if not candidates:
        from inline_agents.backends.openai.custom_providers.whirlpool.translate import (
            _extract_flat_text,
        )

        text = _extract_flat_text(response)
        if text is not None:
            return ChatCompletionMessage(role="assistant", content=text)
        raise WhirlpoolTranslationError(
            f"Whirlpool response missing candidates: keys={list(response.keys())}"
        )

    model = _gemini_model_id()
    completion_response = dict(response)
    if "usageMetadata" not in completion_response and "usage" not in completion_response:
        # LiteLLM's usage mapper requires this key; Whirlpool often omits it.
        completion_response["usageMetadata"] = {}
    try:
        raw_response = httpx.Response(status_code=200, headers={})
        model_response = VertexGeminiConfig()._transform_google_generate_content_to_openai_model_response(
            completion_response=completion_response,
            model_response=ModelResponse(),
            model=model,
            logging_obj=SimpleNamespace(optional_params={}),
            raw_response=raw_response,
        )
    except Exception as exc:
        raise WhirlpoolTranslationError(
            f"LiteLLM Gemini response transform failed: {exc}"
        ) from exc

    return _model_response_to_chat_message(model_response)


def _messages_for_litellm(
    messages: Sequence[ChatCompletionMessageParam],
) -> List[Dict[str, Any]]:
    """Copy chat messages and map Agents extra_content → LiteLLM provider fields.

    Do not insert a fake trailing user turn here: openai-agents 0.6.8 only keeps
    thought signatures on tool calls after the last real user message.
    """
    converted: List[Dict[str, Any]] = []
    unsigned_function_calls = 0
    for message in messages:
        item = _to_plain(message)
        if item.get("role") == "assistant":
            tool_calls = item.get("tool_calls") or []
            rewritten = []
            for tool_call in tool_calls:
                tc = _to_plain(tool_call)
                signature = _thought_signature_from_tool_call(tc)
                if not signature:
                    signature = _SKIP_SIGNATURE_VALIDATION
                    unsigned_function_calls += 1
                provider = dict(tc.get("provider_specific_fields") or {})
                provider["thought_signature"] = signature
                tc["provider_specific_fields"] = provider
                rewritten.append(tc)
            if rewritten:
                item["tool_calls"] = rewritten
        converted.append(item)

    if unsigned_function_calls:
        logger.warning(
            "Whirlpool payload replays %s function call(s) with no Gemini thought "
            "signature; sent the validation-skip sentinel instead",
            unsigned_function_calls,
        )
    return converted


def _agents_tools_to_openai(
    tools: Sequence[Tool] | None,
    handoffs: Sequence[Handoff] | None,
) -> List[Dict[str, Any]]:
    openai_tools: List[Dict[str, Any]] = []
    for tool in tools or []:
        try:
            openai_tools.append(Converter.tool_to_openai(tool))
        except Exception as exc:
            raise WhirlpoolTranslationError(
                f"Whirlpool PoC cannot translate tool type {type(tool)!r}: {exc}"
            ) from exc
    for handoff in handoffs or []:
        openai_tools.append(Converter.convert_handoff_tool(handoff))
    return openai_tools


def _sanitize_payload_tool_schemas(payload: Dict[str, Any]) -> None:
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        declarations = tool.get("functionDeclarations") or tool.get("function_declarations")
        if not isinstance(declarations, list):
            continue
        for declaration in declarations:
            if isinstance(declaration, dict) and "parameters" in declaration:
                declaration["parameters"] = sanitize_json_schema_for_gemini(
                    declaration["parameters"]
                )


def _model_response_to_chat_message(model_response: ModelResponse) -> ChatCompletionMessage:
    choices = getattr(model_response, "choices", None) or []
    if not choices:
        raise WhirlpoolTranslationError("LiteLLM Gemini response had no choices")

    message = getattr(choices[0], "message", None)
    if message is None:
        raise WhirlpoolTranslationError("LiteLLM Gemini response had no message")

    message_dict = _to_plain(message)
    content = message_dict.get("content")
    if isinstance(content, str) and not content.strip():
        content = None

    tool_calls: List[_ToolCallWithThoughtSignature] = []
    pending_signature = _first_message_thought_signature(message_dict)
    for index, tool_call in enumerate(message_dict.get("tool_calls") or []):
        tc = _to_plain(tool_call)
        fn = _to_plain(tc.get("function") or {})
        extra_content = _extra_content_from_provider_fields(tc) or _extra_content_from_provider_fields(
            fn
        )
        if extra_content is None and index == 0 and pending_signature:
            extra_content = {"google": {"thought_signature": pending_signature}}
        tool_calls.append(
            _ToolCallWithThoughtSignature(
                id=str(tc.get("id") or f"call_{index}"),
                type="function",
                function=Function(
                    name=fn.get("name") or "unknown",
                    arguments=fn.get("arguments") or "{}",
                ),
                extra_content=extra_content,
            )
        )

    if tool_calls:
        signed = sum(1 for call in tool_calls if getattr(call, "extra_content", None))
        logger.info(
            "Whirlpool returned %s function call(s), %s carrying a thought signature",
            len(tool_calls),
            signed,
        )

    return ChatCompletionMessage(
        role="assistant",
        content=content,
        tool_calls=tool_calls or None,
    )


def _first_message_thought_signature(message_dict: Dict[str, Any]) -> str | None:
    provider = message_dict.get("provider_specific_fields")
    if not isinstance(provider, dict):
        return None
    signatures = provider.get("thought_signatures")
    if isinstance(signatures, list) and signatures and isinstance(signatures[0], str):
        return signatures[0]
    signature = provider.get("thought_signature")
    if isinstance(signature, str) and signature:
        return signature
    return None


def _extra_content_from_provider_fields(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    provider = obj.get("provider_specific_fields")
    if not isinstance(provider, dict):
        return None
    signature = provider.get("thought_signature")
    if isinstance(signature, str) and signature:
        return {"google": {"thought_signature": signature}}
    return None


def _ensure_content_roles(contents: List[Dict[str, Any]]) -> None:
    """LiteLLM 1.82.0 omitted ``role`` on some contents; Gemini REST needs it."""
    for item in contents:
        if not isinstance(item, dict):
            continue
        if item.get("role") in ("user", "model"):
            continue
        parts = item.get("parts") or []
        has_function_call = any(
            isinstance(part, dict) and ("functionCall" in part or "function_call" in part)
            for part in parts
        )
        item["role"] = "model" if has_function_call else "user"


def _camelize_gemini_payload(obj: Any) -> Any:
    if isinstance(obj, list):
        return [_camelize_gemini_payload(item) for item in obj]
    if isinstance(obj, dict):
        return {
            _GEMINI_KEY_ALIASES.get(key, key): _camelize_gemini_payload(value)
            for key, value in obj.items()
        }
    return obj


def _to_plain(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {key: _to_plain(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(item) for item in obj]
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        try:
            return _to_plain(dump(exclude_none=False))
        except TypeError:
            return _to_plain(dump())
    items = getattr(obj, "items", None)
    if callable(items) and not isinstance(obj, type):
        try:
            return {key: _to_plain(value) for key, value in items()}
        except Exception:
            pass
    return json.loads(json.dumps(obj, default=str))
