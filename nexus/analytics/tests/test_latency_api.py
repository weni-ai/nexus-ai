"""Tests for inline agent latency API auth and query helpers."""

from datetime import date
from unittest import mock
from uuid import uuid4

import pytest
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIRequestFactory

from nexus.analytics.api.permissions import InlineAgentLatencyAPIPermission
from nexus.analytics.latency_phases import cumulative_bucket_key_for_threshold, increment_buckets
from nexus.analytics.latency_queries import build_summary, validate_date_range
from nexus.analytics.models import InlineAgentLatencyHourly


class InlineAgentLatencyAPIPermissionTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.permission = InlineAgentLatencyAPIPermission()
        self.view = mock.Mock()

    @override_settings(INLINE_AGENT_LATENCY_API_TOKEN="latency-secret")
    def test_allows_fixed_service_token(self):
        request = self.factory.get(
            "/api/analytics/inline-agent-latency/summary/",
            HTTP_AUTHORIZATION="Bearer latency-secret",
        )
        self.assertTrue(self.permission.has_permission(request, self.view))

    @override_settings(INLINE_AGENT_LATENCY_API_TOKEN="latency-secret")
    def test_denies_wrong_token(self):
        request = self.factory.get(
            "/api/analytics/inline-agent-latency/summary/",
            HTTP_AUTHORIZATION="Bearer wrong",
        )
        self.assertFalse(self.permission.has_permission(request, self.view))

    @override_settings(INLINE_AGENT_LATENCY_API_TOKEN="latency-secret")
    def test_allows_keycloak_internal_user(self):
        pytest.importorskip("weni_commons")
        from weni_commons.auth import WeniAuthContext

        request = self.factory.get("/api/analytics/inline-agent-latency/summary/")
        request.auth = WeniAuthContext(
            project_uuid=str(uuid4()),
            user_email="staff@example.com",
            token_type="keycloak",
        )
        request.user = mock.Mock(is_authenticated=True)

        with mock.patch(
            "weni_commons.auth.CanCommunicateInternally.has_permission",
            return_value=True,
        ):
            self.assertTrue(self.permission.has_permission(request, self.view))


class LatencyPhasesBucketTestCase(SimpleTestCase):
    def test_cumulative_bucket_key_uses_next_upper_bound(self):
        self.assertEqual(cumulative_bucket_key_for_threshold(18000), "20000")
        self.assertEqual(cumulative_bucket_key_for_threshold(20000), "20000")

    def test_increment_buckets_cumulative(self):
        buckets = increment_buckets({}, 6500)
        self.assertEqual(buckets["10000"], 1)
        self.assertEqual(buckets["inf"], 1)


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

    @override_settings(INLINE_AGENT_LATENCY_TARGET_MS_HIGH=18000)
    def test_build_summary_uses_nearest_cumulative_bucket_for_custom_target(self):
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
        self.assertEqual(summary["pct_under_target_high_ms"], 100.0)
