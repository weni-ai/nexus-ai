"""Translate OpenAI Agents / chat-completions shapes ↔ Gemini generateContent."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from agents.handoffs import Handoff
from agents.models.chatcmpl_converter import Converter
from agents.tool import FunctionTool, Tool
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageParam
from openai.types.chat.chat_completion_message_function_tool_call import (
    ChatCompletionMessageFunctionToolCall,
    Function,
)

logger = logging.getLogger(__name__)


class WhirlpoolTranslationError(Exception):
    """Raised when request/response translation fails or tools are rejected."""


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
                "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
            }
        )

    for handoff in handoffs or []:
        openai_tool = Converter.convert_handoff_tool(handoff)
        fn = openai_tool.get("function") or {}
        declarations.append(
            {
                "name": fn.get("name"),
                "description": fn.get("description") or "",
                "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
            }
        )

    return [d for d in declarations if d.get("name")]


def chat_messages_to_gemini_contents(
    messages: Sequence[ChatCompletionMessageParam],
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Convert OpenAI chat messages to Gemini ``systemInstruction`` + ``contents``."""
    system_parts: List[str] = []
    contents: List[Dict[str, Any]] = []

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
                args = fn.get("arguments") or "{}"
                if isinstance(args, str):
                    try:
                        args_obj = json.loads(args) if args else {}
                    except json.JSONDecodeError:
                        args_obj = {"raw": args}
                else:
                    args_obj = args
                parts.append(
                    {
                        "functionCall": {
                            "name": fn.get("name") or tc.get("id") or "unknown",
                            "args": args_obj,
                        }
                    }
                )
            if parts:
                contents.append({"role": "model", "parts": parts})
            continue

        if role == "tool":
            name = message.get("name") or _tool_name_from_tool_call_id(message.get("tool_call_id"))
            response_payload = message.get("content")
            if isinstance(response_payload, str):
                try:
                    response_obj: Any = json.loads(response_payload)
                except json.JSONDecodeError:
                    response_obj = {"result": response_payload}
            else:
                response_obj = response_payload
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": name or "tool",
                                "response": response_obj
                                if isinstance(response_obj, dict)
                                else {"result": response_obj},
                            }
                        }
                    ],
                }
            )
            continue

        logger.debug("Skipping unsupported chat message role=%s", role)

    system_instruction = None
    if system_parts:
        system_instruction = {"parts": [{"text": "\n\n".join(system_parts)}]}

    if not contents:
        contents = [{"role": "user", "parts": [{"text": ""}]}]

    return system_instruction, contents


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

    for part in parts:
        if not isinstance(part, dict):
            continue
        if "text" in part and part["text"] is not None:
            text_chunks.append(str(part["text"]))
        function_call = part.get("functionCall") or part.get("function_call")
        if function_call:
            name = function_call.get("name") or "unknown"
            args = function_call.get("args") or function_call.get("arguments") or {}
            if not isinstance(args, str):
                args = json.dumps(args, ensure_ascii=False)
            tool_calls.append(
                ChatCompletionMessageFunctionToolCall(
                    id=f"call_{uuid.uuid4().hex[:24]}",
                    type="function",
                    function=Function(name=name, arguments=args),
                )
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
