"""Translate OpenAI Agents / chat-completions shapes ↔ Gemini generateContent."""

from __future__ import annotations

import base64
import json
import logging
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from agents.handoffs import Handoff
from agents.models.chatcmpl_converter import Converter
from agents.tool import FunctionTool, Tool
from django.conf import settings
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageParam
from openai.types.chat.chat_completion_message_function_tool_call import (
    ChatCompletionMessageFunctionToolCall,
    Function,
)

logger = logging.getLogger(__name__)

_TOOL_RESULT_CONTINUATION_TEXT = "Continue using the tool result above."

# Gemini 3 rejects a request whose current turn replays a ``functionCall`` without
# the signature it issued. For calls Gemini never generated (context injected as a
# tool result, history recorded before signatures were kept) Google documents this
# sentinel to skip validation. ``thoughtSignature`` is a bytes field, so base64.
_SKIP_SIGNATURE_VALIDATION = base64.b64encode(b"skip_thought_signature_validator").decode()


class WhirlpoolTranslationError(Exception):
    """Raised when request/response translation fails or tools are rejected."""


class _ToolCallWithThoughtSignature(ChatCompletionMessageFunctionToolCall):
    """Carry Gemini thought signatures through the Agents SDK converter.

    ``Converter.message_to_output_items`` reads ``extra_content.google.thought_signature``.
    The stock OpenAI tool-call type has no such field.
    """

    extra_content: dict[str, Any] | None = None


_GEMINI_SCHEMA_DROP_KEYS = frozenset(
    {
        "title",
        "default",
        "examples",
        "example",
        "$schema",
        "$id",
        "$defs",
        "definitions",
        "additionalProperties",
    }
)
_SCHEMA_UNION_KEYS = ("anyOf", "oneOf")


def sanitize_json_schema_for_gemini(schema: Any) -> Any:
    """Rewrite OpenAI/Pydantic JSON Schema into Gemini ``functionDeclarations`` subset.

    Vertex rejects sibling keys next to ``anyOf`` (Pydantic ``Optional[list]`` plus
    OpenAI ``_clean_schema`` injecting ``type``). Optional ``T | null`` becomes
    ``type`` + ``nullable``. Schema text is never logged.
    """
    if isinstance(schema, list):
        return [sanitize_json_schema_for_gemini(item) for item in schema]
    if not isinstance(schema, dict):
        return schema

    cleaned = {
        key: sanitize_json_schema_for_gemini(value)
        for key, value in schema.items()
        if key not in _GEMINI_SCHEMA_DROP_KEYS
    }
    collapsed = _collapse_nullable_union(cleaned)
    if collapsed is not cleaned:
        return sanitize_json_schema_for_gemini(collapsed)

    union_key = next((key for key in _SCHEMA_UNION_KEYS if key in cleaned), None)
    if union_key:
        # Gemini: no siblings next to anyOf/oneOf (including description/type).
        return {union_key: cleaned[union_key]}

    return cleaned


def _collapse_nullable_union(schema: Dict[str, Any]) -> Dict[str, Any]:
    for key in _SCHEMA_UNION_KEYS:
        options = schema.get(key)
        if not isinstance(options, list):
            continue
        non_null = [option for option in options if not _is_null_schema(option)]
        has_null = any(_is_null_schema(option) for option in options)
        if not has_null or len(non_null) != 1 or not isinstance(non_null[0], dict):
            continue
        collapsed = dict(non_null[0])
        collapsed["nullable"] = True
        description = schema.get("description")
        if description and "description" not in collapsed:
            collapsed["description"] = description
        return collapsed
    return schema


def _is_null_schema(option: Any) -> bool:
    return isinstance(option, dict) and option.get("type") == "null"


def agents_tools_to_gemini(
    tools: Sequence[Tool] | None,
    handoffs: Sequence[Handoff] | None = None,
) -> List[Dict[str, Any]]:
    """Map Agents tools/handoffs to Gemini ``functionDeclarations``."""
    declarations: List[Dict[str, Any]] = []
    for tool in tools or []:
        try:
            openai_tool = Converter.tool_to_openai(tool)
        except Exception as exc:
            raise WhirlpoolTranslationError(
                f"Whirlpool PoC cannot translate tool type {type(tool)!r}: {exc}"
            ) from exc
        fn = openai_tool.get("function") or {}
        declarations.append(
            {
                "name": fn.get("name"),
                "description": fn.get("description") or "",
                "parameters": sanitize_json_schema_for_gemini(
                    fn.get("parameters") or {"type": "object", "properties": {}}
                ),
            }
        )

    for handoff in handoffs or []:
        openai_tool = Converter.convert_handoff_tool(handoff)
        fn = openai_tool.get("function") or {}
        declarations.append(
            {
                "name": fn.get("name"),
                "description": fn.get("description") or "",
                "parameters": sanitize_json_schema_for_gemini(
                    fn.get("parameters") or {"type": "object", "properties": {}}
                ),
            }
        )

    return [d for d in declarations if d.get("name")]


def _part_thought_signature(part: Dict[str, Any]) -> str | None:
    signature = part.get("thoughtSignature") or part.get("thought_signature")
    if isinstance(signature, str) and signature:
        return signature
    return None


def _get_field(obj: Any, key: str) -> Any:
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def _thought_signature_from_tool_call(tool_call: Any) -> str | None:
    extra = _get_field(tool_call, "extra_content")
    if isinstance(extra, dict):
        google_fields = extra.get("google")
        if isinstance(google_fields, dict):
            signature = google_fields.get("thought_signature")
            if isinstance(signature, str) and signature:
                return signature
    provider = _get_field(tool_call, "provider_specific_fields")
    if isinstance(provider, dict):
        signature = provider.get("thought_signature")
        if isinstance(signature, str) and signature:
            return signature
    return None


def chat_messages_to_gemini_contents(
    messages: Sequence[ChatCompletionMessageParam],
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Convert OpenAI chat messages to Gemini ``systemInstruction`` + ``contents``."""
    system_parts: List[str] = []
    contents: List[Dict[str, Any]] = []
    tool_names_by_call_id: Dict[str, str] = {}
    tool_result_content: Optional[Dict[str, Any]] = None
    unsigned_function_calls = 0

    for message in messages:
        role = message.get("role")
        if role in ("system", "developer"):
            text = _content_to_text(message.get("content"))
            if text:
                system_parts.append(text)
            continue

        if role == "user":
            contents.append({"role": "user", "parts": [{"text": _content_to_text(message.get("content"))}]})
            continue

        if role == "assistant":
            parts: List[Dict[str, Any]] = []
            text = _content_to_text(message.get("content"))
            if text:
                parts.append({"text": text})
            for tc in message.get("tool_calls") or []:
                fn = tc.get("function") or {}
                call_id = tc.get("id")
                function_name = fn.get("name") or call_id or "unknown"
                if call_id and fn.get("name"):
                    tool_names_by_call_id[str(call_id)] = str(fn["name"])
                args = fn.get("arguments") or "{}"
                if isinstance(args, str):
                    try:
                        args_obj = json.loads(args) if args else {}
                    except json.JSONDecodeError:
                        args_obj = {"raw": args}
                else:
                    args_obj = args
                function_call_part: Dict[str, Any] = {
                    "functionCall": {
                        "name": function_name,
                        "args": args_obj,
                    }
                }
                thought_signature = _thought_signature_from_tool_call(tc)
                if not thought_signature:
                    thought_signature = _SKIP_SIGNATURE_VALIDATION
                    unsigned_function_calls += 1
                function_call_part["thoughtSignature"] = thought_signature
                parts.append(function_call_part)
            if parts:
                contents.append({"role": "model", "parts": parts})
            continue

        if role == "tool":
            tool_call_id = message.get("tool_call_id")
            name = (
                message.get("name")
                or tool_names_by_call_id.get(str(tool_call_id))
                or _tool_name_from_tool_call_id(tool_call_id)
            )
            response_payload = message.get("content")
            if isinstance(response_payload, str):
                try:
                    response_obj: Any = json.loads(response_payload)
                except json.JSONDecodeError:
                    response_obj = {"result": response_payload}
            else:
                response_obj = response_payload
            response_part = {
                "functionResponse": {
                    "name": name or "tool",
                    "response": response_obj
                    if isinstance(response_obj, dict)
                    else {"result": response_obj},
                }
            }
            # Gemini requires all functionCall parts followed by all functionResponse
            # parts; interleaving them across turns is a 400. Keep results of one
            # round of (possibly parallel) calls in a single user turn.
            if contents and contents[-1] is tool_result_content:
                tool_result_content["parts"].append(response_part)
            else:
                tool_result_content = {"role": "user", "parts": [response_part]}
                contents.append(tool_result_content)
            continue

        logger.debug("Skipping unsupported chat message role=%s", role)

    if unsigned_function_calls:
        logger.warning(
            "Whirlpool payload replays %s function call(s) with no Gemini thought "
            "signature; sent the validation-skip sentinel instead",
            unsigned_function_calls,
        )

    _ensure_gateway_prompt_after_tool_result(contents)

    system_instruction = None
    if system_parts:
        system_instruction = {"parts": [{"text": "\n\n".join(system_parts)}]}

    if not contents:
        contents = [{"role": "user", "parts": [{"text": ""}]}]

    return system_instruction, contents


def _ensure_gateway_prompt_after_tool_result(contents: List[Dict[str, Any]]) -> None:
    """Give Whirlpool's request preprocessor a non-empty final ``text`` part.

    Gemini accepts a user turn ending in ``functionResponse``, but Whirlpool's
    gateway extracts the prompt from ``contents[-1].parts[-1].text`` before
    forwarding the request. Keep the protocol part and append a neutral
    continuation instruction; the original user prompt was already evaluated
    before the tool call.
    """
    if not contents:
        return

    parts = contents[-1].get("parts")
    if not isinstance(parts, list) or not parts:
        return

    last_part = parts[-1]
    if isinstance(last_part, dict) and "functionResponse" in last_part:
        parts.append({"text": _TOOL_RESULT_CONTINUATION_TEXT})


def build_generate_content_payload(
    *,
    messages: Sequence[ChatCompletionMessageParam],
    tools: Sequence[Tool] | None = None,
    handoffs: Sequence[Handoff] | None = None,
    max_tokens: int | None = None,
    tool_choice: Any = None,
) -> Dict[str, Any]:
    system_instruction, contents = chat_messages_to_gemini_contents(messages)
    payload: Dict[str, Any] = {"contents": contents}
    if system_instruction:
        payload["systemInstruction"] = system_instruction

    declarations = agents_tools_to_gemini(tools, handoffs)
    if declarations:
        payload["tools"] = [{"functionDeclarations": declarations}]
        gemini_tool_config = _tool_choice_to_gemini(tool_choice)
        if gemini_tool_config is not None:
            payload["toolConfig"] = gemini_tool_config

    if max_tokens is not None:
        payload["generationConfig"] = {"maxOutputTokens": max_tokens}

    return payload


def gemini_response_to_chat_message(response: Dict[str, Any]) -> ChatCompletionMessage:
    """Map Whirlpool/Gemini generateContent JSON to ChatCompletionMessage."""
    candidates = response.get("candidates") or []
    if not candidates:
        # Some gateways may return a flatter shape; try common alternatives.
        text = _extract_flat_text(response)
        if text is not None:
            return ChatCompletionMessage(role="assistant", content=text)
        raise WhirlpoolTranslationError(
            f"Whirlpool response missing candidates: keys={list(response.keys())}"
        )

    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    text_chunks: List[str] = []
    tool_calls: List[ChatCompletionMessageFunctionToolCall] = []
    pending_thought_signature: str | None = None
    first_function_call = True

    for part in parts:
        if not isinstance(part, dict):
            continue
        part_signature = _part_thought_signature(part)
        function_call = part.get("functionCall") or part.get("function_call")
        is_thought_part = bool(part.get("thought"))

        if part_signature and not function_call:
            pending_thought_signature = pending_thought_signature or part_signature

        if "text" in part and part["text"] is not None and not is_thought_part:
            text_chunks.append(str(part["text"]))

        if function_call:
            name = function_call.get("name") or "unknown"
            args = function_call.get("args") or function_call.get("arguments") or {}
            if not isinstance(args, str):
                args = json.dumps(args, ensure_ascii=False)
            thought_signature = part_signature
            if not thought_signature and first_function_call:
                thought_signature = pending_thought_signature
            first_function_call = False
            pending_thought_signature = None
            extra_content = None
            if thought_signature:
                extra_content = {"google": {"thought_signature": thought_signature}}
            tool_calls.append(
                _ToolCallWithThoughtSignature(
                    id=f"call_{uuid.uuid4().hex[:24]}",
                    type="function",
                    function=Function(name=name, arguments=args),
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
        content="\n".join(text_chunks) if text_chunks else None,
        tool_calls=tool_calls or None,
    )


def assert_tools_accepted(
    *,
    requested_tool_names: Iterable[str],
    request_payload: Dict[str, Any],
    response: Dict[str, Any],
) -> None:
    """Fail loudly if tools were requested but the gateway clearly stripped support.

    Whirlpool may omit echo of tool schemas; we only raise when the response itself
    signals an unsupported-tools error. Callers should also treat HTTP 4xx from the
    client as hard failures.
    """
    requested = list(requested_tool_names)
    if not requested:
        return

    err = response.get("error") or {}
    message = ""
    if isinstance(err, dict):
        message = str(err.get("message") or err.get("status") or "")
    elif isinstance(err, str):
        message = err

    lowered = message.lower()
    if any(token in lowered for token in ("tool", "function", "unsupported", "not support")):
        raise WhirlpoolTranslationError(
            "Whirlpool rejected or does not support tool/function calling required "
            f"by inline agents. Requested tools={requested}. Error={message!r}. "
            f"Request had tools={bool(request_payload.get('tools'))}"
        )


def guard_block_message(status_code: int | None, body: Any) -> Optional[str]:
    """Return the guard text when a 400 body carries a configured block message.

    Whirlpool used to answer guard blocks with HTTP 200 plus the message; it now answers 400.
    Only an exact match against ``settings.WHIRLPOOL_GUARD_BLOCK_MESSAGES`` is relayed as a
    model reply, so real Bad Request failures keep surfacing as errors.
    """
    if status_code != 400:
        return None

    configured = [
        message.strip()
        for message in (getattr(settings, "WHIRLPOOL_GUARD_BLOCK_MESSAGES", None) or [])
        if isinstance(message, str) and message.strip()
    ]
    if not configured:
        return None

    for candidate in _error_message_candidates(body):
        for message in configured:
            if candidate.strip() == message:
                return message
    return None


def _error_message_candidates(body: Any) -> List[str]:
    if isinstance(body, str):
        return [body]
    if not isinstance(body, dict):
        return []

    candidates: List[str] = []
    for key in ("error_description", "message", "description", "detail", "error"):
        value = body.get(key)
        if isinstance(value, str):
            candidates.append(value)
        elif isinstance(value, dict):
            for nested_key in ("message", "description", "error_description"):
                nested = value.get(nested_key)
                if isinstance(nested, str):
                    candidates.append(nested)
    return candidates


def _tool_choice_to_gemini(tool_choice: Any) -> Optional[Dict[str, Any]]:
    if tool_choice is None:
        return None
    if tool_choice == "none":
        return {"functionCallingConfig": {"mode": "NONE"}}
    if tool_choice == "required":
        return {"functionCallingConfig": {"mode": "ANY"}}
    if tool_choice == "auto":
        return {"functionCallingConfig": {"mode": "AUTO"}}
    if isinstance(tool_choice, str):
        return {
            "functionCallingConfig": {
                "mode": "ANY",
                "allowedFunctionNames": [tool_choice],
            }
        }
    if isinstance(tool_choice, dict):
        fn = (tool_choice.get("function") or {}).get("name")
        if fn:
            return {
                "functionCallingConfig": {
                    "mode": "ANY",
                    "allowedFunctionNames": [fn],
                }
            }
    return {"functionCallingConfig": {"mode": "AUTO"}}


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text") or "")
                elif "text" in item:
                    parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    return str(content)


def _tool_name_from_tool_call_id(tool_call_id: Any) -> Optional[str]:
    if not tool_call_id:
        return None
    return str(tool_call_id)


def _extract_flat_text(response: Dict[str, Any]) -> Optional[str]:
    for key in ("text", "output", "message", "content"):
        value = response.get(key)
        if isinstance(value, str):
            return value
    return None


def openai_tool_names(tools: Sequence[Tool] | None, handoffs: Sequence[Handoff] | None = None) -> List[str]:
    names: List[str] = []
    for tool in tools or []:
        if isinstance(tool, FunctionTool):
            names.append(tool.name)
        else:
            names.append(getattr(tool, "name", type(tool).__name__))
    for handoff in handoffs or []:
        names.append(handoff.tool_name)
    return names
