"""Tests for conversation SQS emission on inline_message:received."""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from router.tasks.inline_message_observers import InlineMessageReceivedMetricsObserver


class InlineMessageReceivedMetricsObserverTests(SimpleTestCase):
    @patch("router.tasks.inline_message_observers.get_conversation_events_producer")
    def test_sends_message_sent_when_not_preview(self, mock_get_producer):
        producer = MagicMock()
        mock_get_producer.return_value = producer

        InlineMessageReceivedMetricsObserver().perform(
            project_uuid="proj",
            contact_urn="urn:x",
            channel_uuid="ch-1",
            contact_name="n",
            message_text="hi",
            response_text="bye",
            incoming_created_at="2026-01-01T00:00:00Z",
            outgoing_created_at="2026-01-01T00:00:01Z",
            preview=False,
        )

        producer.send_event.assert_called_once()

    def test_preview_skips_producer(self):
        with patch("router.tasks.inline_message_observers.get_conversation_events_producer") as mock_get:
            InlineMessageReceivedMetricsObserver().perform(
                project_uuid="proj",
                contact_urn="urn:x",
                channel_uuid="ch-1",
                contact_name="n",
                message_text="hi",
                response_text="bye",
                incoming_created_at="2026-01-01T00:00:00Z",
                outgoing_created_at="2026-01-01T00:00:01Z",
                preview=True,
            )
            mock_get.assert_not_called()

    def test_skip_conversation_sqs_skips_producer(self):
        with patch("router.tasks.inline_message_observers.get_conversation_events_producer") as mock_get:
            InlineMessageReceivedMetricsObserver().perform(
                project_uuid="proj",
                contact_urn="urn:x",
                channel_uuid="ch-1",
                contact_name="n",
                message_text="hi",
                response_text="bye",
                incoming_created_at="2026-01-01T00:00:00Z",
                outgoing_created_at="2026-01-01T00:00:01Z",
                preview=False,
                skip_conversation_sqs=True,
            )
            mock_get.assert_not_called()
