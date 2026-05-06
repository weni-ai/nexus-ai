import hashlib
import json
import logging
import string
import uuid
from typing import Any, Dict, List, Optional

import boto3
import sentry_sdk
from django.conf import settings

logger = logging.getLogger(__name__)

# SQS FIFO MessageDeduplicationId: max 128 chars, alphanumeric + hyphen
SQS_DEDUP_ID_MAX_LENGTH = 128
# SQS FIFO MessageGroupId max length
SQS_GROUP_ID_MAX_LENGTH = 128

# Ref: AWS SQS — MessageGroupId ≤128 chars, alphanumeric + punctuation (ASCII).
# string.punctuation matches the documented AWS punctuation set for this parameter.
_MESSAGE_GROUP_ID_ALLOWED = frozenset(string.ascii_letters + string.digits + string.punctuation)


def _message_group_id_needs_hashed_suffix(prefix: str, contact_urn: str) -> bool:
    """
    True when the literal group id is too long or contains characters outside the SQS
    allowlist (e.g. spaces). Naive substitution would merge distinct URNs such as
    "a b" and "a-b", so we use a digest suffix instead.
    """
    combined = prefix + contact_urn
    if len(combined) > SQS_GROUP_ID_MAX_LENGTH:
        return True
    return any(c not in _MESSAGE_GROUP_ID_ALLOWED for c in combined)


def _fifo_message_group_digest_suffix(project_uuid: str, channel_uuid: str, contact_urn: str) -> str:
    """Full SHA-256 hex digest of project:channel:urn (UTF-8); caller truncates for MessageGroupId."""
    raw = f"{project_uuid}:{channel_uuid}:{contact_urn}".encode()
    return hashlib.sha256(raw).hexdigest()


def _fifo_message_group_id(project_uuid: str, channel_uuid: str, contact_urn: str) -> str:
    """
    Build a FIFO MessageGroupId scoped by project and channel.

    Uses project_uuid:channel_uuid:contact_urn when it fits ≤128 chars and matches
    AWS allowed characters. Otherwise uses a deterministic SHA-256 hex suffix so
    length and invalid characters (e.g. spaces) are safe without merging different
    URNs that would collide after naive replacement.
    """
    prefix = f"{project_uuid}:{channel_uuid}:"
    if _message_group_id_needs_hashed_suffix(prefix, contact_urn):
        digest = _fifo_message_group_digest_suffix(project_uuid, channel_uuid, contact_urn)
        # If project/channel strings contain disallowed chars, do not prepend them — SQS would reject.
        prefix_safe = all(c in _MESSAGE_GROUP_ID_ALLOWED for c in prefix)
        if not prefix_safe:
            return digest[:SQS_GROUP_ID_MAX_LENGTH]
        max_suffix = SQS_GROUP_ID_MAX_LENGTH - len(prefix)
        if max_suffix < 1:
            return digest[:SQS_GROUP_ID_MAX_LENGTH]
        return prefix + digest[:max_suffix]

    return prefix + contact_urn


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

        event_type = payload.get("event_type", "message.received")
        raw_correlation = payload.get("correlation_id") or str(uuid.uuid4())
        dedup_source = f"{event_type}:{raw_correlation}"
        message_deduplication_id = _normalize_sqs_deduplication_id(dedup_source)

        message_group_id = _fifo_message_group_id(project_uuid, channel_uuid, contact_urn)
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
                MessageDeduplicationId=message_deduplication_id,
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
