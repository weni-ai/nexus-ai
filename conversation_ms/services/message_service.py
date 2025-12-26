"""
Message service for Conversation MS (Prototype).

This service will handle message processing logic.
Currently a placeholder for future implementation.
"""

import logging

logger = logging.getLogger(__name__)


class MessageService:
    """Service for processing messages in Conversation MS."""

    def process_message_received(self, event_data: dict):
        """
        Process a message.received event.

        Args:
            event_data: Event data dictionary
        """
        logger.debug("[MessageService] Processing message.received", extra={"event_data": event_data})

    def process_message_sent(self, event_data: dict):
        """
        Process a message.sent event.

        Args:
            event_data: Event data dictionary
        """
        logger.debug("[MessageService] Processing message.sent", extra={"event_data": event_data})
