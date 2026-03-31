"""
DTO for SQS message events consumed by the conversation microservice.

Structure: event_type, correlation_id, data (project_uuid, contact_urn,
channel_uuid, message with id, text, source, created_at, contact_name).
All fields are required.
"""

import json
import uuid
from dataclasses import dataclass
from typing import Optional

EVENT_TYPE_MESSAGE_RECEIVED = "message.received"
EVENT_TYPE_MESSAGE_SENT = "message.sent"


def sqs_response_text_from_agent_output(response: str, *, skip_dispatch: bool) -> str:
    """
    Text used in message.sent (via notify_async → observers) for SQS.

    When skip_dispatch is True, agent output is often JSON with is_final_output and messages_sent;
    we join messages_sent[].text with newlines for the conversation microservice. Otherwise
    return response unchanged.
    """
    if not skip_dispatch or not (response or "").strip():
        return response
    try:
        parsed = json.loads(response)
    except (json.JSONDecodeError, TypeError):
        return response
    if not isinstance(parsed, dict):
        return response
    messages_sent = parsed.get("messages_sent")
    if not isinstance(messages_sent, list):
        return response
    parts: list[str] = []
    for item in messages_sent:
        if isinstance(item, dict):
            t = str(item.get("text", "")).strip()
            if t:
                parts.append(t)
    if not parts:
        return response
    return "\n".join(parts)


@dataclass(frozen=True)
class MessagePayload:
    id: str
    text: str
    source: str
    created_at: str
    contact_name: str


@dataclass
class EventData:
    project_uuid: str
    contact_urn: str
    channel_uuid: str
    message: Optional[MessagePayload] = None
    key: Optional[str] = None
    value: Optional[str] = None


@dataclass
class SQSMessageEvent:
    event_type: str
    correlation_id: str
    data: EventData

    def to_dict(self):
        data = {
            "project_uuid": self.data.project_uuid,
            "contact_urn": self.data.contact_urn,
            "channel_uuid": self.data.channel_uuid,
        }

        if self.data.message:
            data["message"] = {
                "id": self.data.message.id,
                "text": self.data.message.text,
                "source": self.data.message.source,
                "created_at": self.data.message.created_at,
                "contact_name": self.data.message.contact_name,
            }

        if self.data.key:
            data["key"] = self.data.key

        if self.data.value:
            data["value"] = self.data.value

        return {
            "event_type": self.event_type,
            "correlation_id": self.correlation_id,
            "data": data,
        }


def _build_dummy_message(contact_name: str = "System") -> MessagePayload:
    """Create a dummy message payload for events that require one."""
    return MessagePayload(
        id=str(uuid.uuid4()),
        text="",
        source="system",
        created_at="",  # Consumer handles empty/missing dates
        contact_name=contact_name,
    )


def build_message_received_event(
    project_uuid: str,
    contact_urn: str,
    channel_uuid: str,
    contact_name: str,
    message_text: str,
    created_at: str,
    message_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> SQSMessageEvent:
    """Build message.received. Pass message_id/correlation_id for SQS and consumer deduplication."""
    cid = correlation_id or str(uuid.uuid4())
    mid = message_id or str(uuid.uuid4())
    return SQSMessageEvent(
        event_type=EVENT_TYPE_MESSAGE_RECEIVED,
        correlation_id=cid,
        data=EventData(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            message=MessagePayload(
                id=mid,
                text=message_text,
                source="incoming",
                created_at=created_at,
                contact_name=contact_name,
            ),
        ),
    )


def build_message_sent_event(
    project_uuid: str,
    contact_urn: str,
    channel_uuid: str,
    contact_name: str,
    message_text: str,
    created_at: str,
    message_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> SQSMessageEvent:
    """Build message.sent. message_id = trace id; correlation_id for SQS dedup."""
    cid = correlation_id or str(uuid.uuid4())
    mid = message_id or str(uuid.uuid4())
    return SQSMessageEvent(
        event_type=EVENT_TYPE_MESSAGE_SENT,
        correlation_id=cid,
        data=EventData(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            message=MessagePayload(
                id=mid,
                text=message_text,
                source="outgoing",
                created_at=created_at,
                contact_name=contact_name,
            ),
        ),
    )


def build_csat_event(
    project_uuid: str,
    contact_urn: str,
    channel_uuid: str,
    value: str,
    contact_name: str = "System",
) -> SQSMessageEvent:
    """Build a CSAT event (piggybacks on message.received)."""
    return SQSMessageEvent(
        event_type=EVENT_TYPE_MESSAGE_RECEIVED,
        correlation_id=str(uuid.uuid4()),
        data=EventData(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            message=_build_dummy_message(contact_name),
            key="weni_csat",
            value=str(value),
        ),
    )


def build_nps_event(
    project_uuid: str,
    contact_urn: str,
    channel_uuid: str,
    value: str,
    contact_name: str = "System",
) -> SQSMessageEvent:
    """Build an NPS event (piggybacks on message.received)."""
    return SQSMessageEvent(
        event_type=EVENT_TYPE_MESSAGE_RECEIVED,
        correlation_id=str(uuid.uuid4()),
        data=EventData(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            message=_build_dummy_message(contact_name),
            key="weni_nps",
            value=str(value),
        ),
    )


def build_custom_event(
    project_uuid: str,
    contact_urn: str,
    channel_uuid: str,
    key: str,
    value: str,
    contact_name: str = "System",
) -> SQSMessageEvent:
    """Build a custom event (piggybacks on message.received)."""
    return SQSMessageEvent(
        event_type=EVENT_TYPE_MESSAGE_RECEIVED,
        correlation_id=str(uuid.uuid4()),
        data=EventData(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            message=_build_dummy_message(contact_name),
            key=key,
            value=str(value),
        ),
    )


def build_inline_message_sqs_events(
    project_uuid: str,
    contact_urn: str,
    channel_uuid: str,
    contact_name: str,
    message_text: str,
    response_text: str,
    incoming_created_at: str,
    outgoing_created_at: str,
    message_conversation_log_uuid: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> list[dict]:
    """Build received + sent events. Incoming is sent on receive; this is for legacy callers."""
    received = build_message_received_event(
        project_uuid=project_uuid,
        contact_urn=contact_urn,
        channel_uuid=channel_uuid,
        contact_name=contact_name,
        message_text=message_text,
        created_at=incoming_created_at,
        message_id=turn_id,
        correlation_id=turn_id,
    )
    sent = build_message_sent_event(
        project_uuid=project_uuid,
        contact_urn=contact_urn,
        channel_uuid=channel_uuid,
        contact_name=contact_name,
        message_text=response_text,
        created_at=outgoing_created_at,
        message_id=message_conversation_log_uuid,
        correlation_id=f"{turn_id}:outgoing" if turn_id else None,
    )
    return [received.to_dict(), sent.to_dict()]
