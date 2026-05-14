"""Merge assistant text with streaming-captured component tool args (formatter replacement)."""

from __future__ import annotations

import ast
import json
import re
import uuid
from typing import Any

COMPONENT_TOOL_NAMES = frozenset(
    {
        "create_quick_replies_message",
        "create_list_message",
        "create_cta_message",
    }
)


def try_parse_output(raw_output: Any) -> Any:
    if isinstance(raw_output, (dict, list)):
        return raw_output
    if isinstance(raw_output, str):
        try:
            return json.loads(raw_output)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(raw_output)
            except (ValueError, SyntaxError):
                pass
    return raw_output


def split_simple_text(text: str, limit: int = 4096) -> list:
    """Split long plain text into multiple channel messages."""
    if len(text) <= limit:
        return [{"msg": {"text": text}}]

    messages: list = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            messages.append({"msg": {"text": remaining}})
            break

        sentences = re.split(r"(?<=[.!?])\s+", remaining)
        chunk = ""
        idx = 0
        while idx < len(sentences) and len(chunk + sentences[idx]) <= limit:
            chunk += sentences[idx] + " "
            idx += 1

        if chunk:
            messages.append({"msg": {"text": chunk.strip()}})
            remaining = " ".join(sentences[idx:])
        else:
            messages.append({"msg": {"text": remaining[:limit]}})
            remaining = remaining[limit:]
    return messages


def smart_text_split(text: str, limit: int) -> tuple[str, str]:
    """Return (simple_text, component_text) for long assistant text next to a component."""
    simple_text_limit = 4096

    if len(text) <= limit:
        return "", text

    sentences = re.split(r"(?<=[.!?])\s+", text)

    for num_sentences in range(1, min(4, len(sentences) + 1)):
        candidate = " ".join(sentences[-num_sentences:])
        remaining = " ".join(sentences[:-num_sentences])
        if len(candidate) <= limit and len(remaining) <= simple_text_limit:
            return remaining.strip(), candidate.strip()

    for num_sentences in range(4, len(sentences) + 1):
        candidate = " ".join(sentences[-num_sentences:])
        remaining = " ".join(sentences[:-num_sentences])
        if len(remaining) <= simple_text_limit:
            if len(candidate) <= limit:
                return remaining.strip(), candidate.strip()
            return remaining.strip(), candidate[:limit].strip()

    if len(sentences) > 1:
        simple = " ".join(sentences[:-1])[:simple_text_limit]
        return simple.strip(), sentences[-1][:limit].strip()

    return text[:simple_text_limit].strip(), text[simple_text_limit : simple_text_limit + limit].strip()


def build_component_msg(agent_text: str, component_args: dict, tool_name: str) -> list:
    """Combine assistant text with structured fields from a streaming component tool."""
    component_fields: dict = {}
    if tool_name == "create_quick_replies_message":
        component_fields["quick_replies"] = component_args.get("quick_replies", [])
    elif tool_name == "create_list_message":
        raw_items = component_args.get("list_items", [])
        list_items = []
        for item in raw_items:
            list_items.append(
                {
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                    "uuid": str(uuid.uuid4()),
                }
            )
        component_fields["interaction_type"] = "list"
        component_fields["list_message"] = {
            "button_text": component_args.get("button_text", "Options"),
            "list_items": list_items,
        }
    elif tool_name == "create_cta_message":
        component_fields["interaction_type"] = "cta_url"
        component_fields["cta_message"] = {
            "display_text": component_args.get("display_text", "Open"),
            "url": component_args.get("url", ""),
        }

    if component_args.get("header_text"):
        component_fields["header"] = {"type": "text", "text": component_args["header_text"]}
    if component_args.get("footer"):
        component_fields["footer"] = component_args["footer"]

    if len(agent_text) > 1024:
        simple_text, comp_text = smart_text_split(agent_text, 1024)
        messages = []
        if simple_text:
            messages.append({"msg": {"text": simple_text}})
        msg = {"text": comp_text}
        msg.update(component_fields)
        messages.append({"msg": msg})
        return messages

    msg = {"text": agent_text}
    msg.update(component_fields)
    return [{"msg": msg}]


def _last_streaming_component_from_new_items(new_items: Any) -> tuple[dict | None, str | None]:
    last_args: dict | None = None
    last_name: str | None = None
    if not new_items:
        return None, None
    for item in new_items:
        if not hasattr(item, "type") or item.type != "tool_call_item":
            continue
        if not hasattr(item, "raw_item") or not hasattr(item.raw_item, "name"):
            continue
        tn = item.raw_item.name
        if tn not in COMPONENT_TOOL_NAMES:
            continue
        try:
            args = json.loads(item.raw_item.arguments)
            last_args = args
            last_name = tn
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue
    return last_args, last_name


def _last_streaming_component_from_tool_calls(tool_calls: dict | None) -> tuple[dict | None, str | None]:
    if not tool_calls:
        return None, None
    for name, args_json in reversed(list(tool_calls.items())):
        if name not in COMPONENT_TOOL_NAMES:
            continue
        try:
            args = json.loads(args_json) if isinstance(args_json, str) else args_json
            if isinstance(args, dict):
                return args, name
        except (json.JSONDecodeError, TypeError):
            continue
    return None, None


def merge_streaming_components_response(
    supervisor_output: Any,
    new_items: Any,
    tool_calls: dict | None = None,
) -> str:
    """
    Build the same JSON string the formatter LLM would return: list[dict] serialized.

    ``supervisor_output`` is ``result.final_output`` (may be str, list, or structured).
    """
    parsed_output = try_parse_output(supervisor_output)

    if isinstance(parsed_output, dict) and parsed_output.get("is_final_output"):
        return json.dumps(parsed_output, ensure_ascii=False)

    if (
        isinstance(parsed_output, list)
        and len(parsed_output) > 0
        and isinstance(parsed_output[0], dict)
        and "msg" in parsed_output[0]
    ):
        response = parsed_output
    else:
        last_args, last_name = _last_streaming_component_from_new_items(new_items)
        if last_args is None and tool_calls:
            last_args, last_name = _last_streaming_component_from_tool_calls(tool_calls)
        if last_args is not None and last_name is not None:
            agent_text = supervisor_output if isinstance(supervisor_output, str) else str(supervisor_output)
            response = build_component_msg(agent_text, last_args, last_name)
        elif isinstance(supervisor_output, str):
            response = split_simple_text(supervisor_output)
        else:
            response = split_simple_text(
                str(supervisor_output) if supervisor_output else "Sorry, the request could not be processed."
            )

    return json.dumps(response, ensure_ascii=False)
