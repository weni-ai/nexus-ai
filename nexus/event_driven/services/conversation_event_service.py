import logging
import uuid
from datetime import datetime
from typing import Dict, Optional

import pendulum
from django.conf import settings

from nexus.event_driven.publisher.sqs_publisher import SQSPublisher

logger = logging.getLogger(__name__)


class ConversationEventService:
    """Service for sending conversation events to Conversation MS via SQS."""

    def __init__(self):
        self.publisher = SQSPublisher()

    def _create_event(
        self,
        event_type: str,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: Optional[str],
        data: Dict,
        correlation_id: Optional[str] = None,
    ) -> Dict:
        """
        Create standardized event structure.

        Args:
            event_type: Type of event (message.received, message.sent, etc.)
            project_uuid: Project UUID
            contact_urn: Contact URN
            channel_uuid: Channel UUID (optional)
            data: Event-specific data
            correlation_id: Correlation ID (optional, will generate if not provided)

        Returns:
            Event dictionary
        """
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        return {
            "event_type": event_type,
            "correlation_id": correlation_id,
            "timestamp": pendulum.now().to_iso8601_string(),
            "data": data,
        }

    def send_message_received_event(
        self,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: Optional[str],
        message_text: str,
        message_id: str,
        message_source: str,
        message_created_at: datetime,
        contact_name: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send message.received event when a message arrives from Mailroom.

        Args:
            project_uuid: Project UUID
            contact_urn: Contact URN
            channel_uuid: Channel UUID
            message_text: Message text content
            message_id: Unique message ID
            message_source: Message source (user/agent)
            message_created_at: Message creation timestamp
            contact_name: Contact name (optional)
            correlation_id: Correlation ID (optional)

        Returns:
            Message ID from SQS if successful, None otherwise
        """
        if not settings.SQS_CONVERSATION_ENABLED:
            return None

        data = {
            "project_uuid": project_uuid,
            "contact_urn": contact_urn,
            "channel_uuid": channel_uuid,
            "message": {
                "message_id": message_id,
                "text": message_text,
                "source": message_source,
                "created_at": message_created_at.isoformat()
                if isinstance(message_created_at, datetime)
                else message_created_at,
            },
        }

        if contact_name:
            data["contact_name"] = contact_name

        event = self._create_event(
            event_type="message.received",
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            data=data,
            correlation_id=correlation_id,
        )

        try:
            message_id = self.publisher.send_message(
                body=event,
                event_type="message.received",
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                channel_uuid=channel_uuid,
                correlation_id=event["correlation_id"],
            )

            logger.info(
                "[ConversationEventService] Message received event sent",
                extra={
                    "sqs_message_id": message_id,
                    "correlation_id": event["correlation_id"],
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "channel_uuid": channel_uuid,
                },
            )

            return message_id

        except Exception as e:
            logger.error(
                "[ConversationEventService] Failed to send message.received event",
                extra={
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "channel_uuid": channel_uuid,
                    "error": str(e),
                },
                exc_info=True,
            )
            return None

    def send_message_sent_event(
        self,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: Optional[str],
        message_text: str,
        message_id: str,
        message_created_at: datetime,
        correlation_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send message.sent event when a response message is generated.

        Args:
            project_uuid: Project UUID
            contact_urn: Contact URN
            channel_uuid: Channel UUID
            message_text: Response message text
            message_id: Unique message ID
            message_created_at: Message creation timestamp
            correlation_id: Correlation ID (optional)

        Returns:
            Message ID from SQS if successful, None otherwise
        """
        if not settings.SQS_CONVERSATION_ENABLED:
            return None

        data = {
            "project_uuid": project_uuid,
            "contact_urn": contact_urn,
            "channel_uuid": channel_uuid,
            "message": {
                "message_id": message_id,
                "text": message_text,
                "source": "agent",
                "created_at": message_created_at.isoformat()
                if isinstance(message_created_at, datetime)
                else message_created_at,
            },
        }

        event = self._create_event(
            event_type="message.sent",
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            data=data,
            correlation_id=correlation_id,
        )

        try:
            message_id = self.publisher.send_message(
                body=event,
                event_type="message.sent",
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                channel_uuid=channel_uuid,
                correlation_id=event["correlation_id"],
            )

            logger.info(
                "[ConversationEventService] Message sent event sent",
                extra={
                    "sqs_message_id": message_id,
                    "correlation_id": event["correlation_id"],
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "channel_uuid": channel_uuid,
                },
            )

            return message_id

        except Exception as e:
            logger.error(
                "[ConversationEventService] Failed to send message.sent event",
                extra={
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "channel_uuid": channel_uuid,
                    "error": str(e),
                },
                exc_info=True,
            )
            return None
