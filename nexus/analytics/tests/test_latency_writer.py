"""Tests for inline agent latency persistence."""

from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase, TestCase

from nexus.analytics.latency_conversation_lookup import build_conversation_lookup
from nexus.analytics.latency_phases import increment_buckets
from nexus.analytics.latency_writer import decide_outlier_sample
from nexus.analytics.models import InlineAgentLatencyHourly, InlineAgentTurnOutlier


class LatencyPhasesTestCase(SimpleTestCase):
    def test_increment_buckets_cumulative(self):
        buckets = increment_buckets({}, 6500)
        self.assertEqual(buckets["10000"], 1)
        self.assertEqual(buckets["inf"], 1)
        self.assertEqual(buckets.get("5000", 0), 0)


class OutlierRulesTestCase(SimpleTestCase):
    def test_threshold_30s(self):
        cfg = {
            "outlier_ms": 30000,
            "broker_outlier_ms": 2000,
            "elevated_ms": 15000,
            "sample_rate": 0,
            "elevated_sample_rate": 0,
        }
        store, reason = decide_outlier_sample(status="success", total_ms=31000, broker_wait_ms=0, cfg=cfg)
        self.assertTrue(store)
        self.assertEqual(reason, "threshold")

    def test_failed_always_stored(self):
        cfg = {"outlier_ms": 30000, "broker_outlier_ms": 2000, "elevated_ms": 15000, "sample_rate": 0, "elevated_sample_rate": 0}
        store, reason = decide_outlier_sample(status="failed", total_ms=100, broker_wait_ms=0, cfg=cfg)
        self.assertTrue(store)
        self.assertEqual(reason, "failed")


class ConversationLookupTestCase(SimpleTestCase):
    def test_builds_window(self):
        finished = datetime(2026, 7, 16, 19, 17, 4, tzinfo=timezone.utc)
        lookup = build_conversation_lookup(
            project_uuid=str(uuid4()),
            contact_urn="telegram:123",
            turn_finished_at=finished,
            turn_id="turn-abc",
        )
        self.assertEqual(lookup["service"], "nexus-conversations")
        self.assertEqual(lookup["correlation_id"], "turn-abc")


class LatencyWriterIntegrationTestCase(TestCase):
    @patch("nexus.analytics.latency_writer.random.random", return_value=0.99)
    def test_record_turn_creates_rollup(self, _mock_random):
        from nexus.analytics.latency_writer import TurnCorrelation, record_turn_latency

        project_uuid = str(uuid4())
        record_turn_latency(
            project_uuid=project_uuid,
            status="success",
            total_seconds=3.5,
            phase_seconds={"orchestration": 0.09, "agent_execution": 2.8},
            correlation=TurnCorrelation(contact_urn="telegram:1"),
            task_id="celery-1",
            turn_id="turn-1",
            enqueued_at=1000.0,
            started_at=1000.05,
            finished_at=datetime(2026, 7, 16, 19, 0, 0, tzinfo=timezone.utc),
        )
        total_row = InlineAgentLatencyHourly.objects.get(project_uuid=project_uuid, phase="total")
        self.assertEqual(total_row.turn_count, 1)
        self.assertEqual(total_row.sum_ms, 3500)
        self.assertEqual(InlineAgentTurnOutlier.objects.filter(project_uuid=project_uuid).count(), 0)

    @patch("nexus.analytics.latency_writer.random.random", return_value=0.99)
    def test_slow_turn_creates_outlier(self, _mock_random):
        from nexus.analytics.latency_writer import TurnCorrelation, record_turn_latency

        project_uuid = str(uuid4())
        record_turn_latency(
            project_uuid=project_uuid,
            status="success",
            total_seconds=35.0,
            phase_seconds={},
            correlation=TurnCorrelation(contact_urn="telegram:2"),
            task_id="celery-2",
            turn_id="turn-2",
            finished_at=datetime(2026, 7, 16, 20, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(InlineAgentTurnOutlier.objects.filter(project_uuid=project_uuid).count(), 1)
