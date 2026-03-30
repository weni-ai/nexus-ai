import json
import logging
import uuid
from typing import Any, Dict, List, Optional

import boto3
import sentry_sdk
from django.conf import settings

logger = logging.getLogger(__name__)

# SQS FIFO MessageDeduplicationId: max 128 chars, alphanumeric + hyphen
SQS_DEDUP_ID_MAX_LENGTH = 128
# SQS FIFO MessageGroupId max length (same as conversation_ms billing producer)
SQS_GROUP_ID_MAX_LENGTH = 128


def _fifo_message_group_id(channel_uuid: str, contact_urn: str) -> str:
    raw = f"{channel_uuid}:{contact_urn}"
    if len(raw) <= SQS_GROUP_ID_MAX_LENGTH:
        return raw
    return raw[:SQS_GROUP_ID_MAX_LENGTH]


def _normalize_sqs_deduplication_id(value: str) -> str:
    """Ensure value is safe for SQS MessageDeduplicationId (<=128 chars, alphanumeric + hyphen)."""
    if not value:
        return str(uuid.uuid4())
    if len(value) <= SQS_DEDUP_ID_MAX_LENGTH and all(c.isalnum() or c == "-" for c in value):
        return value
    truncated = value[:SQS_DEDUP_ID_MAX_LENGTH]
    safe = "".join(c if c.isalnum() or c == "-" else "-" for c in truncated)
    return safe or str(uuid.uuid4())


class ConversationEventsSQSProducer:
    """Send conversation event payloads to SQS FIFO queue."""

    def __init__(
        self,
        queue_url: Optional[str] = None,
        region_name: Optional[str] = None,
    ):
        self._queue_url = queue_url or settings.CONVERSATION_EVENTS_SQS_QUEUE_URL
        self._region_name = region_name or settings.CONVERSATION_EVENTS_SQS_REGION
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client("sqs", region_name=self._region_name)
        return self._client

    def send_event(self, payload: Dict[str, Any]) -> None:
        """Send a single event to the FIFO queue. Raises on failure."""
        data = payload["data"]
        project_uuid = data["project_uuid"]
        contact_urn = data["contact_urn"]
        channel_uuid = data["channel_uuid"]

        correlation_id = _normalize_sqs_deduplication_id(payload.get("correlation_id") or str(uuid.uuid4()))
        event_type = payload.get("event_type", "message.received")

        message_group_id = _fifo_message_group_id(channel_uuid, contact_urn)
        message_attributes = {
            "event_type": {"StringValue": event_type, "DataType": "String"},
            "project_uuid": {"StringValue": project_uuid, "DataType": "String"},
            "channel_uuid": {"StringValue": channel_uuid, "DataType": "String"},
        }

        try:
            client = self._get_client()
            client.send_message(
                QueueUrl=self._queue_url,
                MessageBody=json.dumps(payload, default=str),
                MessageGroupId=message_group_id,
                MessageDeduplicationId=correlation_id,
                MessageAttributes=message_attributes,
            )
            logger.debug("Sent conversation event to SQS: %s", event_type)
        except Exception as e:
            logger.error("Failed to send conversation event to SQS: %s", e, exc_info=True)
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.set_tag("contact_urn", contact_urn)
            sentry_sdk.set_tag("channel_uuid", channel_uuid)
            sentry_sdk.set_context("payload", payload)
            sentry_sdk.capture_exception(e)
            raise

    def send_events(self, events: List[Dict[str, Any]]) -> None:
        """Send each event to the queue. Stops on first failure (raises)."""
        for event in events:
            self.send_event(event)


def get_conversation_events_producer() -> ConversationEventsSQSProducer:
    """Return the default producer (queue URL and region from settings)."""
    return ConversationEventsSQSProducer()
