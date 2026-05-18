from __future__ import annotations

import json
import re
from typing import Any, List, Optional

from agents import FunctionTool, RunContextWrapper
from pydantic import BaseModel, Field, field_validator

STREAMING_COMPONENT_ACK = json.dumps({"streaming_component_ack": True}, ensure_ascii=False)

_STREAMING_NAMES = frozenset(
    {
        "create_quick_replies_message",
        "create_list_message",
        "create_cta_message",
    }
)


def _clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return value
    cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", value).strip()
    return cleaned or None


class QuickRepliesArgs(BaseModel):
    """Arguments for quick replies component (2-3 options). No text field — agent writes text separately."""

    quick_replies: List[str] = Field(
        ...,
        min_length=2,
        max_length=3,
        description="List of 2-3 quick reply options, maximum 20 characters each",
    )
    header_text: Optional[str] = Field(None, max_length=60, description="Optional header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    @field_validator("quick_replies")
    @classmethod
    def validate_quick_replies(cls, v: List[str]) -> List[str]:
        for i, option in enumerate(v):
            if len(option) > 20:
                v[i] = option[:20]
        return v

    @field_validator("header_text")
    @classmethod
    def clean_header(cls, v: Optional[str]) -> Optional[str]:
        return _clean_text(v)

    @field_validator("footer")
    @classmethod
    def clean_footer(cls, v: Optional[str]) -> Optional[str]:
        return _clean_text(v)


class ListItemArgs(BaseModel):
    """Single list item (title + description)."""

    title: str = Field(..., max_length=24, description="Item title, maximum 24 characters")
    description: str = Field(..., max_length=72, description="Item description, maximum 72 characters")


class ListMessageArgs(BaseModel):
    """Arguments for list component (2-10 options with descriptions). No text field — agent writes text separately."""

    button_text: str = Field(..., max_length=20, description="Button text, maximum 20 characters")
    list_items: List[ListItemArgs] = Field(
        ...,
        min_length=2,
        max_length=10,
        description="List of 2-10 items with title and description",
    )
    header_text: Optional[str] = Field(None, max_length=60, description="Optional header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    @field_validator("header_text")
    @classmethod
    def clean_header(cls, v: Optional[str]) -> Optional[str]:
        return _clean_text(v)

    @field_validator("footer")
    @classmethod
    def clean_footer(cls, v: Optional[str]) -> Optional[str]:
        return _clean_text(v)


class CtaMessageArgs(BaseModel):
    """Arguments for Call to Action component with URL. No text field — agent writes text separately."""

    url: str = Field(..., description="Valid URL for redirection")
    display_text: str = Field(..., max_length=20, description="Button text, maximum 20 characters")
    header_text: Optional[str] = Field(None, max_length=60, description="Optional header text, maximum 60 characters")
    footer: Optional[str] = Field(None, max_length=60, description="Optional footer, maximum 60 characters")

    @field_validator("header_text")
    @classmethod
    def clean_header(cls, v: Optional[str]) -> Optional[str]:
        return _clean_text(v)

    @field_validator("footer")
    @classmethod
    def clean_footer(cls, v: Optional[str]) -> Optional[str]:
        return _clean_text(v)


async def _streaming_quick_replies(ctx: RunContextWrapper[Any], args: str) -> str:
    QuickRepliesArgs.model_validate_json(args)
    return STREAMING_COMPONENT_ACK


async def _streaming_list(ctx: RunContextWrapper[Any], args: str) -> str:
    ListMessageArgs.model_validate_json(args)
    return STREAMING_COMPONENT_ACK


async def _streaming_cta(ctx: RunContextWrapper[Any], args: str) -> str:
    CtaMessageArgs.model_validate_json(args)
    return STREAMING_COMPONENT_ACK


_QUICK_REPLIES_DESCRIPTION = (
    "Registers 2-3 quick reply buttons to attach to your text response.\n\n"
    "USE WHEN: Your instructions explicitly tell you to present 2-3 simple options "
    "(<=20 chars each, NO descriptions).\n\n"
    "DO NOT USE: If ANY option needs a description -> use create_list_message. "
    "If 4+ options -> use create_list_message.\n\n"
    "IMPORTANT: Do NOT include your response text in this tool. Write your full text "
    "response normally - the buttons will be attached automatically.\n\n"
    "ONE COMPONENT ONLY: Never call this tool together with another component tool in the same response.\n\n"
    "header_text / footer: Leave null unless strictly needed. All greetings, explanations, and "
    "instructions belong in your text output, not here."
)

_LIST_MESSAGE_DESCRIPTION = (
    "Registers a selectable list of 2-10 items (title + description) to attach to your text response.\n\n"
    "USE WHEN: 4+ options (mandatory), OR 2-3 options with descriptions, OR options >20 chars.\n\n"
    "DO NOT USE: If 2-3 simple options without descriptions -> use create_quick_replies_message.\n\n"
    "IMPORTANT: Do NOT include your response text in this tool. Write your full text response "
    "normally - the list will be attached automatically.\n\n"
    "LIMITS: title <=24 chars, description <=72 chars, button_text <=20 chars\n\n"
    "ONE COMPONENT ONLY: Never call this tool together with another component tool in the same response.\n\n"
    "header_text / footer: Leave null unless strictly needed. All greetings, explanations, questions, "
    "and instructions belong in your text output, not in header_text or footer."
)

_CTA_MESSAGE_DESCRIPTION = (
    "MANDATORY tool for delivering a single URL to the customer. Registers a clickable CTA button "
    "attached to your text response.\n\n"
    "USE WHEN: Your response needs to share exactly 1 URL. This is the ONLY way to deliver a clickable "
    "link — raw URLs in text are not rendered as clickable by the channel.\n\n"
    "DO NOT USE: If 2+ different URLs need to be shared -> include them directly in your text instead "
    "(this tool only supports 1 URL). Also skip if no URL is needed.\n\n"
    "IMPORTANT: Do NOT include the URL in your text output. Write your full text response naturally "
    "(describe the link, e.g. 'Access our portal:') and place the URL exclusively in this tool call. "
    "The button will be attached automatically below your text.\n\n"
    "LIMITS: display_text <=20 chars\n\n"
    "ONE COMPONENT ONLY: Never call this tool together with another component tool in the same response.\n\n"
    "header_text / footer: Leave null unless strictly needed. All greetings, explanations, and "
    "instructions belong in your text output, not in header_text or footer."
)


def get_supervisor_component_tools_for_streaming_merge(
    formatter_tools_descriptions: dict | None = None,
) -> list:
    """
    Build the three streaming component tools exposed to the new manager.

    ``formatter_tools_descriptions`` is consulted only as an optional description override
    keyed by tool name — useful for per-project tweaks coming from the supervisor row.
    Shapes (Pydantic models) are fixed regardless of overrides.
    """
    overrides: dict = formatter_tools_descriptions or {}

    quick_replies_tool = FunctionTool(
        name="create_quick_replies_message",
        description=overrides.get("create_quick_replies_message", _QUICK_REPLIES_DESCRIPTION),
        params_json_schema=QuickRepliesArgs.model_json_schema(),
        on_invoke_tool=_streaming_quick_replies,
    )
    list_message_tool = FunctionTool(
        name="create_list_message",
        description=overrides.get("create_list_message", _LIST_MESSAGE_DESCRIPTION),
        params_json_schema=ListMessageArgs.model_json_schema(),
        on_invoke_tool=_streaming_list,
    )
    cta_message_tool = FunctionTool(
        name="create_cta_message",
        description=overrides.get("create_cta_message", _CTA_MESSAGE_DESCRIPTION),
        params_json_schema=CtaMessageArgs.model_json_schema(),
        on_invoke_tool=_streaming_cta,
    )

    return [quick_replies_tool, list_message_tool, cta_message_tool]


def streaming_merge_tool_names(formatter_tools_descriptions: dict | None = None) -> frozenset[str]:
    """Tool names injected by ``get_supervisor_component_tools_for_streaming_merge`` (for deduping DB tools)."""
    return _STREAMING_NAMES


__all__ = [
    "STREAMING_COMPONENT_ACK",
    "_STREAMING_NAMES",
    "CtaMessageArgs",
    "ListItemArgs",
    "ListMessageArgs",
    "QuickRepliesArgs",
    "get_supervisor_component_tools_for_streaming_merge",
    "streaming_merge_tool_names",
]
