"""Tests for inline agent turn latency recording (Phase 0)."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import SimpleTestCase
from prometheus_client import REGISTRY

from router.tasks.inline_agent_metrics import INLINE_AGENT_TURN_MISSING_PROJECT_UUID_TOTAL
from router.tasks.latency_context import (
    PHASE_ORCHESTRATION,
    TURN_STATUS_SUCCESS,
    TurnLatencyRecorder,
    parse_valid_project_uuid,
    record_cache_access,
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

    def test_finish_observes_metrics_with_valid_project_uuid(self):
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

        samples = REGISTRY.get_sample_value(
            "inline_agent_turn_duration_seconds_count",
            labels={"status": TURN_STATUS_SUCCESS, "project_uuid": self.project_uuid},
        )
        self.assertEqual(samples, 1.0)

    @patch("router.tasks.latency_context.sentry_sdk.capture_message")
    def test_missing_project_uuid_skips_histograms(self, mock_capture):
        before = INLINE_AGENT_TURN_MISSING_PROJECT_UUID_TOTAL._value.get()
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
        after = INLINE_AGENT_TURN_MISSING_PROJECT_UUID_TOTAL._value.get()
        self.assertEqual(after, before + 1)

    def test_finish_is_idempotent(self):
        recorder = TurnLatencyRecorder(
            project_uuid=self.project_uuid,
            turn_id=self.turn_id,
            task_id=self.task_id,
        )
        recorder.finish(TURN_STATUS_SUCCESS)
        recorder.finish(TURN_STATUS_SUCCESS)
        samples = REGISTRY.get_sample_value(
            "inline_agent_turn_duration_seconds_count",
            labels={"status": TURN_STATUS_SUCCESS, "project_uuid": self.project_uuid},
        )
        self.assertEqual(samples, 1.0)


class CacheAccessMetricsTestCase(SimpleTestCase):
    def test_record_cache_access_valid_project(self):
        project_uuid = str(uuid4())
        record_cache_access(project_uuid, "data", True)
        samples = REGISTRY.get_sample_value(
            "inline_agent_cache_access_total",
            labels={"cache_type": "data", "hit": "true", "project_uuid": project_uuid},
        )
        self.assertEqual(samples, 1.0)

    def test_record_cache_access_invalid_project_skipped(self):
        before = REGISTRY.get_sample_value(
            "inline_agent_cache_access_total",
            labels={"cache_type": "data", "hit": "true", "project_uuid": "bad"},
        )
        record_cache_access("bad-id", "data", True)
        after = REGISTRY.get_sample_value(
            "inline_agent_cache_access_total",
            labels={"cache_type": "data", "hit": "true", "project_uuid": "bad"},
        )
        self.assertEqual(before, after)
