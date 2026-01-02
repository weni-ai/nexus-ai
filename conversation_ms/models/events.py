from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class MessageReceivedEvent:
    correlation_id: str
    project_uuid: str
    contact_urn: str
    channel_uuid: Optional[str]
    message: Dict[str, Any]
    timestamp: datetime

    @classmethod
    def from_sqs_event(cls, event_data: dict) -> "MessageReceivedEvent":
        data = event_data.get("data", {})
        message = data.get("message", {})

        created_at_str = message.get("created_at", "")
        timestamp = datetime.utcnow()
        if created_at_str:
            try:
                created_at_str = created_at_str.replace("Z", "+00:00")
                timestamp = datetime.fromisoformat(created_at_str)
                if timestamp.tzinfo:
                    timestamp = timestamp.replace(tzinfo=None)
            except (ValueError, AttributeError):
                pass

        return cls(
            correlation_id=event_data.get("correlation_id", ""),
            project_uuid=data.get("project_uuid", ""),
            contact_urn=data.get("contact_urn", ""),
            channel_uuid=data.get("channel_uuid"),
            message=message,
            timestamp=timestamp,
        )


@dataclass
class MessageSentEvent:
    correlation_id: str
    project_uuid: str
    contact_urn: str
    channel_uuid: Optional[str]
    message: Dict[str, Any]
    timestamp: datetime

    @classmethod
    def from_sqs_event(cls, event_data: dict) -> "MessageSentEvent":
        data = event_data.get("data", {})
        message = data.get("message", {})

        created_at_str = message.get("created_at", "")
        timestamp = datetime.utcnow()
        if created_at_str:
            try:
                created_at_str = created_at_str.replace("Z", "+00:00")
                timestamp = datetime.fromisoformat(created_at_str)
                if timestamp.tzinfo:
                    timestamp = timestamp.replace(tzinfo=None)
            except (ValueError, AttributeError):
                pass

        return cls(
            correlation_id=event_data.get("correlation_id", ""),
            project_uuid=data.get("project_uuid", ""),
            contact_urn=data.get("contact_urn", ""),
            channel_uuid=data.get("channel_uuid"),
            message=message,
            timestamp=timestamp,
        )
