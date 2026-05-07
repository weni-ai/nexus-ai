"""Tests for conversation SQS emission on inline_message:received."""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from router.tasks.inline_message_observers import (
    InlineMessageReceivedMetricsObserver,
    _should_emit_conversation_outgoing_sqs,
)


class ShouldEmitConversationOutgoingSqsTests(SimpleTestCase):
    def test_missing_task_id_allows_emit(self):
        self.assertTrue(_should_emit_conversation_outgoing_sqs("p1", "urn:1", None))
        self.assertTrue(_should_emit_conversation_outgoing_sqs("p1", "urn:1", ""))

    @patch("router.tasks.inline_message_observers.RedisTaskManager")
    def test_matching_latest_allows_emit(self, mock_tm_cls):
        mock_tm = MagicMock()
        mock_tm.get_latest_task_id.return_value = "task-a"
        mock_tm_cls.return_value = mock_tm
        self.assertTrue(_should_emit_conversation_outgoing_sqs("p1", "urn:1", "task-a"))

    @patch("router.tasks.inline_message_observers.RedisTaskManager")
    def test_mismatch_latest_blocks_emit(self, mock_tm_cls):
        mock_tm = MagicMock()
        mock_tm.get_latest_task_id.return_value = "task-b"
        mock_tm_cls.return_value = mock_tm
        self.assertFalse(_should_emit_conversation_outgoing_sqs("p1", "urn:1", "task-a"))


class InlineMessageReceivedMetricsObserverTests(SimpleTestCase):
    @patch("router.tasks.inline_message_observers.get_conversation_events_producer")
    @patch("router.tasks.inline_message_observers.RedisTaskManager")
    def test_sends_when_latest_matches(self, mock_tm_cls, mock_get_producer):
        mock_tm = MagicMock()
        mock_tm.get_latest_task_id.return_value = "tid-1"
        mock_tm_cls.return_value = mock_tm
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
            celery_task_id="tid-1",
        )

        producer.send_event.assert_called_once()

    @patch("router.tasks.inline_message_observers.get_conversation_events_producer")
    @patch("router.tasks.inline_message_observers.RedisTaskManager")
    def test_skips_send_when_superseded(self, mock_tm_cls, mock_get_producer):
        mock_tm = MagicMock()
        mock_tm.get_latest_task_id.return_value = "tid-newer"
        mock_tm_cls.return_value = mock_tm
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
            celery_task_id="tid-stale",
        )

        producer.send_event.assert_not_called()

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
                celery_task_id="tid-1",
            )
            mock_get.assert_not_called()
