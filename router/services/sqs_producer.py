"""
SQS producer for conversation events (message.received, message.sent).

Sends event payloads to the configured queue when CONVERSATION_EVENTS_SQS_QUEUE_URL is set.
"""

import json
import logging
from typing import Any, Dict, List

import boto3
from django.conf import settings

logger = logging.getLogger(__name__)


class ConversationEventsSQSProducer:
    """Send conversation event payloads to Amazon SQS."""

    def __init__(
        self,
        queue_url: str = None,
        region_name: str = None,
    ):
        self._queue_url = queue_url or getattr(settings, "CONVERSATION_EVENTS_SQS_QUEUE_URL", "")
        self._region_name = region_name or getattr(settings, "CONVERSATION_EVENTS_SQS_REGION", "us-east-1")
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client("sqs", region_name=self._region_name)
        return self._client

    def is_enabled(self) -> bool:
        return bool(self._queue_url)

    def send_event(self, payload: Dict[str, Any]) -> None:
        """Send a single event dict as JSON to the queue. No-op if queue URL not set."""
        if not self.is_enabled():
            logger.debug("SQS producer disabled (no CONVERSATION_EVENTS_SQS_QUEUE_URL)")
            return

        try:
            client = self._get_client()
            client.send_message(
                QueueUrl=self._queue_url,
                MessageBody=json.dumps(payload, default=str),
            )
            logger.debug(
                "Sent event to SQS: %s",
                payload.get("event_type", "unknown"),
            )
        except Exception as e:
            logger.error(
                "Failed to send conversation event to SQS: %s",
                e,
                exc_info=True,
                extra={"event_type": payload.get("event_type"), "queue_url": self._queue_url},
            )
            raise

    def send_events(self, events: List[Dict[str, Any]]) -> None:
        """Send each event to the queue. Stops on first failure (raises)."""
        for event in events:
            self.send_event(event)


def get_conversation_events_producer() -> ConversationEventsSQSProducer:
    """Return the default producer (queue URL and region from settings)."""
    return ConversationEventsSQSProducer()
