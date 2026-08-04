"""Tests for inline agent latency query helpers."""

from datetime import date
from uuid import uuid4

from django.test import TestCase

from nexus.analytics.latency_queries import build_summary, validate_date_range
from nexus.analytics.models import InlineAgentLatencyHourly


class LatencyQueriesTestCase(TestCase):
    def test_validate_date_range_max_90_days(self):
        start = date(2026, 1, 1)
        end = date(2026, 6, 1)
        self.assertIsNotNone(validate_date_range(start, end))

    def test_build_summary_aggregates(self):
        project_uuid = uuid4()
        InlineAgentLatencyHourly.objects.create(
            project_uuid=project_uuid,
            hour_ts="2026-07-16T19:00:00+00:00",
            execution_path="inline_agents",
            phase="total",
            turn_count=2,
            sum_ms=7000,
            max_ms=4000,
            buckets={"20000": 2, "30000": 2, "inf": 2},
        )
        summary = build_summary(project_uuid, date(2026, 7, 16), date(2026, 7, 16))
        self.assertEqual(summary["turn_count"], 2)
        self.assertEqual(summary["avg_ms"], 3500.0)
        self.assertEqual(summary["pct_under_target_high_ms"], 100.0)
