"""
DTO for SQS message events consumed by the conversation microservice.

Structure: event_type, correlation_id, data (project_uuid, contact_urn,
channel_uuid, message with id, text, source, created_at, contact_name).
All fields are required.
"""

import uuid
from dataclasses import dataclass

EVENT_TYPE_MESSAGE_RECEIVED = "message.received"
EVENT_TYPE_MESSAGE_SENT = "message.sent"


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
    message: MessagePayload


@dataclass
class SQSMessageEvent:
    event_type: str
    correlation_id: str
    data: EventData

    def to_dict(self):
        return {
            "event_type": self.event_type,
            "correlation_id": self.correlation_id,
            "data": {
                "project_uuid": self.data.project_uuid,
                "contact_urn": self.data.contact_urn,
                "channel_uuid": self.data.channel_uuid,
                "message": {
                    "id": self.data.message.id,
                    "text": self.data.message.text,
                    "source": self.data.message.source,
                    "created_at": self.data.message.created_at,
                    "contact_name": self.data.message.contact_name,
                },
            },
        }


def build_message_received_event(
    project_uuid: str,
    contact_urn: str,
    channel_uuid: str,
    contact_name: str,
    message_text: str,
    created_at: str,
) -> SQSMessageEvent:
    return SQSMessageEvent(
        event_type=EVENT_TYPE_MESSAGE_RECEIVED,
        correlation_id=str(uuid.uuid4()),
        data=EventData(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            message=MessagePayload(
                id=str(uuid.uuid4()),
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
) -> SQSMessageEvent:
    return SQSMessageEvent(
        event_type=EVENT_TYPE_MESSAGE_SENT,
        correlation_id=str(uuid.uuid4()),
        data=EventData(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            message=MessagePayload(
                id=str(uuid.uuid4()),
                text=message_text,
                source="outgoing",
                created_at=created_at,
                contact_name=contact_name,
            ),
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
) -> list[dict]:
    received = build_message_received_event(
        project_uuid=project_uuid,
        contact_urn=contact_urn,
        channel_uuid=channel_uuid,
        contact_name=contact_name,
        message_text=message_text,
        created_at=incoming_created_at,
    )
    sent = build_message_sent_event(
        project_uuid=project_uuid,
        contact_urn=contact_urn,
        channel_uuid=channel_uuid,
        contact_name=contact_name,
        message_text=response_text,
        created_at=outgoing_created_at,
    )
    return [received.to_dict(), sent.to_dict()]
