"""Tests for inline agent turn latency recording."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import SimpleTestCase

from router.tasks.latency_context import (
    PHASE_ORCHESTRATION,
    TURN_STATUS_SUCCESS,
    TurnLatencyRecorder,
    parse_valid_project_uuid,
)


class ParseValidProjectUuidTestCase(SimpleTestCase):
    def test_valid_uuid(self):
        uid = str(uuid4())
        self.assertEqual(parse_valid_project_uuid(uid), uid)

    def test_invalid_uuid(self):
        self.assertIsNone(parse_valid_project_uuid("not-a-uuid"))
        self.assertIsNone(parse_valid_project_uuid(""))
        self.assertIsNone(parse_valid_project_uuid(None))


class TurnLatencyRecorderTestCase(SimpleTestCase):
    def setUp(self):
        self.project_uuid = str(uuid4())
        self.turn_id = "turn-123"
        self.task_id = "task-456"

    @patch("router.tasks.latency_context.record_turn_latency")
    def test_finish_persists_latency_with_valid_project_uuid(self, mock_record):
        recorder = TurnLatencyRecorder(
            project_uuid=self.project_uuid,
            turn_id=self.turn_id,
            task_id=self.task_id,
            _enqueued_at=1000.0,
            _started_at=1001.5,
        )
        with recorder.phase(PHASE_ORCHESTRATION):
            pass
        recorder.finish(TURN_STATUS_SUCCESS)

        mock_record.assert_called_once()
        kwargs = mock_record.call_args.kwargs
        self.assertEqual(kwargs["project_uuid"], self.project_uuid)
        self.assertEqual(kwargs["status"], TURN_STATUS_SUCCESS)
        self.assertIn(PHASE_ORCHESTRATION, kwargs["phase_seconds"])

    @patch("router.tasks.latency_context.record_turn_latency")
    @patch("router.tasks.latency_context.sentry_sdk.capture_message")
    def test_missing_project_uuid_skips_persistence(self, mock_capture, mock_record):
        recorder = TurnLatencyRecorder.from_message_and_request(
            message={"text": "hello"},
            request=MagicMock(id="task-1", headers={}),
            turn_id=self.turn_id,
        )
        with recorder.phase(PHASE_ORCHESTRATION):
            pass
        recorder.finish(TURN_STATUS_SUCCESS)

        self.assertFalse(recorder.metrics_enabled)
        mock_capture.assert_called_once()
        mock_record.assert_not_called()

    @patch("router.tasks.latency_context.record_turn_latency")
    def test_finish_is_idempotent(self, mock_record):
        recorder = TurnLatencyRecorder(
            project_uuid=self.project_uuid,
            turn_id=self.turn_id,
            task_id=self.task_id,
        )
        recorder.finish(TURN_STATUS_SUCCESS)
        recorder.finish(TURN_STATUS_SUCCESS)
        mock_record.assert_called_once()
