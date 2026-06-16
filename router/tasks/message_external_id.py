"""Resolve Flows/WWC message identifiers from router payloads."""

from __future__ import annotations

from typing import Any, Mapping


def resolve_msg_external_id(message: Mapping[str, Any]) -> str:
    """
    Resolve the message id used for grpc streaming and typing indicators.

    Flows may send the canonical id as msg_external_id, msg_uuid, or msg_id depending
    on channel type (WWC simulation often omits msg_external_id).
    """
    msg_event = message.get("msg_event") or {}
    if not isinstance(msg_event, dict):
        msg_event = {}
    metadata = message.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    explicit = msg_event.get("msg_external_id")
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()

    for source in (msg_event, metadata):
        for key in ("msg_uuid", "uuid", "message_uuid", "message_id"):
            value = source.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()

    msg_id = msg_event.get("msg_id")
    if msg_id is not None and str(msg_id).strip():
        return str(msg_id).strip()

    return ""


def enrich_message_msg_external_id(message: dict[str, Any]) -> dict[str, Any]:
    """Copy message and set msg_event.msg_external_id when a fallback id is available."""
    processed = message.copy()
    resolved = resolve_msg_external_id(processed)
    if not resolved:
        return processed

    msg_event = dict(processed.get("msg_event") or {})
    if not str(msg_event.get("msg_external_id") or "").strip():
        msg_event["msg_external_id"] = resolved
        processed["msg_event"] = msg_event
    return processed
