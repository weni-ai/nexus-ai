"""
Supervisor component tools for streaming + merge: quick_replies, list, cta return a small ack so the
run continues; other tools keep formatter-era behavior. Merge happens in OpenAIBackend after the stream.
"""

from __future__ import annotations

import json
from typing import Any

from agents import FunctionTool, RunContextWrapper

from inline_agents.backends.openai.components_tools import (
    CtaMessageArgs,
    ListMessageArgs,
    QuickRepliesArgs,
    get_component_tools,
)

STREAMING_COMPONENT_ACK = json.dumps({"streaming_component_ack": True}, ensure_ascii=False)

_STREAMING_NAMES = frozenset(
    {
        "create_quick_replies_message",
        "create_list_message",
        "create_cta_message",
    }
)


async def _streaming_quick_replies(ctx: RunContextWrapper[Any], args: str) -> str:
    QuickRepliesArgs.model_validate_json(args)
    return STREAMING_COMPONENT_ACK


async def _streaming_list(ctx: RunContextWrapper[Any], args: str) -> str:
    ListMessageArgs.model_validate_json(args)
    return STREAMING_COMPONENT_ACK


async def _streaming_cta(ctx: RunContextWrapper[Any], args: str) -> str:
    CtaMessageArgs.model_validate_json(args)
    return STREAMING_COMPONENT_ACK


def get_supervisor_component_tools_for_streaming_merge(
    formatter_tools_descriptions: dict | None = None,
) -> list:
    """
    Full component toolset with streaming variants for quick replies, list, and CTA.
    """
    base_tools = get_component_tools(formatter_tools_descriptions)
    out: list = []
    for tool in base_tools:
        name = getattr(tool, "name", None)
        if name == "create_quick_replies_message":
            t = FunctionTool(
                name="create_quick_replies_message",
                description=tool.description,
                params_json_schema=QuickRepliesArgs.model_json_schema(),
                on_invoke_tool=_streaming_quick_replies,
            )
            out.append(t)
        elif name == "create_list_message":
            t = FunctionTool(
                name="create_list_message",
                description=tool.description,
                params_json_schema=ListMessageArgs.model_json_schema(),
                on_invoke_tool=_streaming_list,
            )
            out.append(t)
        elif name == "create_cta_message":
            t = FunctionTool(
                name="create_cta_message",
                description=tool.description,
                params_json_schema=CtaMessageArgs.model_json_schema(),
                on_invoke_tool=_streaming_cta,
            )
            out.append(t)
        else:
            out.append(tool)
    return out


__all__ = [
    "STREAMING_COMPONENT_ACK",
    "_STREAMING_NAMES",
    "get_supervisor_component_tools_for_streaming_merge",
]
