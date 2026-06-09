from unittest import mock
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.inline_agents.backends.openai.models import ManagerAgent
from nexus.inline_agents.models import Agent, IntegratedAgent
from nexus.projects.api.resolution_rate_views import ProjectsResolutionRateView
from nexus.projects.models import Project
from nexus.projects.services.projects_resolution_rate import (
    CONVERSATIONS_METRICS_EARLIEST_DATE,
    _agent_counts,
    apply_include_blocks,
    build_result_rows,
    parse_calendar_date,
    parse_page_size,
    resolution_rate_from_counts,
    resolve_calendar_range,
    sort_result_rows,
)
from nexus.usecases.intelligences.tests.intelligence_factory import IntegratedIntelligenceFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.users.tests.user_factory import UserFactory

SUMMARY_PAYLOAD = {
    "start_date": "2026-05-19",
    "end_date": "2026-05-25",
    "average_resolution_rate": 0.5,
    "average_csat": 4.0,
    "average_nps": 8.0,
    "projects": [],
}


def _summary_for_projects(projects_metrics):
    return {
        **SUMMARY_PAYLOAD,
        "projects": projects_metrics,
    }


@mock.patch("nexus.projects.api.resolution_rate_views.ConversationsRESTClient.get_projects_resolution_summary")
class TestProjectsResolutionRateView(TestCase):
    def setUp(self):
        integrated = IntegratedIntelligenceFactory()
        self.eligible_project = integrated.project
        self.eligible_project.inline_agent_switch = True
        self.eligible_project.save(update_fields=["inline_agent_switch"])

        self.ab1_project = Project.objects.create(
            name="AB 1 Project",
            org=self.eligible_project.org,
            created_by=self.eligible_project.created_by,
            inline_agent_switch=False,
        )

        self.manager = ManagerAgent.objects.create(
            name="Manager X",
            base_prompt="Manager prompt",
            release_date=timezone.now(),
            foundation_model="gpt-4",
            model_vendor="openai",
            collaborators_foundation_model="gpt-4o-mini",
            formatter_agent_foundation_model="gpt-4o-mini",
        )
        self.eligible_project.manager_agent = self.manager
        self.eligible_project.use_components = True
        self.eligible_project.save(update_fields=["manager_agent", "use_components"])

        self.custom_agent = Agent.objects.create(
            name="Custom",
            slug="custom-agent",
            project=self.eligible_project,
            instruction="i",
            collaboration_instructions="c",
            is_official=False,
        )
        IntegratedAgent.objects.create(
            agent=self.custom_agent,
            project=self.eligible_project,
            is_active=True,
        )

        self.catalog_project = Project.objects.create(
            name="Official Catalog",
            org=self.eligible_project.org,
            created_by=self.eligible_project.created_by,
            inline_agent_switch=True,
        )
        self.catalog_official_agent = Agent.objects.create(
            name="Catalog Official",
            slug="catalog-official-agent",
            project=self.catalog_project,
            instruction="i",
            collaboration_instructions="c",
            is_official=True,
        )
        IntegratedAgent.objects.create(
            agent=self.catalog_official_agent,
            project=self.eligible_project,
            is_active=True,
        )

        self.internal_user = UserFactory()
        ct = ContentType.objects.get_for_model(self.internal_user)
        perm, _ = Permission.objects.get_or_create(
            codename="can_communicate_internally",
            name="can communicate internally",
            content_type=ct,
        )
        self.internal_user.user_permissions.add(perm)
        self.internal_user = type(self.internal_user).objects.get(pk=self.internal_user.pk)

        self.factory = APIRequestFactory()
        self.view = ProjectsResolutionRateView.as_view()
        self.url = reverse("projects-resolution-rate-v2")

    def _get(self, params=None, user=None):
        request = self.factory.get(self.url, data=params or {})
        force_authenticate(request, user=user or self.internal_user)
        return self.view(request)

    def test_requires_internal_permission(self, mock_summary):
        response = self._get(user=UserFactory())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_summary.assert_not_called()

    def test_invalid_project_uuid_returns_400(self, mock_summary):
        response = self._get({"project_uuids": "not-a-uuid"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_summary.assert_not_called()

    def test_invalid_date_returns_400(self, mock_summary):
        response = self._get({"start_date": "bad-date"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_summary.assert_not_called()

    def test_partial_date_range_returns_400(self, mock_summary):
        response = self._get({"start_date": "2026-05-01"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_summary.assert_not_called()

    def test_start_date_before_go_live_returns_400(self, mock_summary):
        response = self._get(
            {
                "project_uuids": str(self.eligible_project.uuid),
                "start_date": "2026-03-27",
                "end_date": "2026-05-25",
            }
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        assert "start_date" in response.data
        mock_summary.assert_not_called()

    def test_end_date_before_go_live_returns_400(self, mock_summary):
        response = self._get(
            {
                "project_uuids": str(self.eligible_project.uuid),
                "start_date": "2026-04-01",
                "end_date": "2026-03-27",
            }
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        assert "end_date" in response.data
        mock_summary.assert_not_called()

    def test_invalid_page_size_returns_400(self, mock_summary):
        response = self._get({"project_uuids": str(self.eligible_project.uuid), "page_size": "0"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        assert "page_size" in response.data
        mock_summary.assert_not_called()

    def test_client_called_with_single_batch_not_per_project(self, mock_summary):
        other = Project.objects.create(
            name="Batch Other",
            org=self.eligible_project.org,
            created_by=self.eligible_project.created_by,
            inline_agent_switch=True,
        )
        mock_summary.return_value = _summary_for_projects([])
        self._get(
            {
                "project_uuids": f"{self.eligible_project.uuid},{other.uuid}",
                "start_date": "2026-05-19",
                "end_date": "2026-05-25",
            }
        )
        mock_summary.assert_called_once()
        called_uuids = set(mock_summary.call_args.kwargs["project_uuids"])
        self.assertEqual(
            called_uuids,
            {str(self.eligible_project.uuid), str(other.uuid)},
        )

    def test_success_merges_conversations_and_local_metadata(self, mock_summary):
        mock_summary.return_value = _summary_for_projects(
            [
                {
                    "project_uuid": str(self.eligible_project.uuid),
                    "conversation_count": 10,
                    "resolved_count": 8,
                    "unresolved_count": 1,
                    "human_support_count": 1,
                    "resolution_rate": 0.8,
                    "csat": 4.5,
                    "csat_responses_count": 2,
                    "nps": 9.0,
                    "nps_responses_count": 1,
                }
            ]
        )
        response = self._get(
            {
                "project_uuids": str(self.eligible_project.uuid),
                "start_date": "2026-05-19",
                "end_date": "2026-05-25",
            }
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.data["results"][0]
        self.assertEqual(row["project_name"], self.eligible_project.name)
        self.assertEqual(row["manager"], "Manager X")
        self.assertTrue(row["uses_components"])
        self.assertEqual(row["custom_agents_count"], 1)
        self.assertEqual(row["official_agents_count"], 1)
        self.assertEqual(row["conversation_count"], 10)
        self.assertEqual(response.data["average_resolution_rate"], 0.8)
        mock_summary.assert_called_once()

    def test_filters_only_ab2_inline_agent_switch_projects(self, mock_summary):
        mock_summary.return_value = _summary_for_projects(
            [
                {
                    "project_uuid": str(self.eligible_project.uuid),
                    "conversation_count": 1,
                    "resolved_count": 1,
                    "unresolved_count": 0,
                    "human_support_count": 0,
                    "resolution_rate": 1.0,
                    "csat": None,
                    "csat_responses_count": 0,
                    "nps": None,
                    "nps_responses_count": 0,
                }
            ]
        )
        response = self._get(
            {
                "project_uuids": f"{self.eligible_project.uuid},{self.ab1_project.uuid}",
                "start_date": "2026-05-19",
                "end_date": "2026-05-25",
            }
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        called_uuids = mock_summary.call_args.kwargs["project_uuids"]
        self.assertEqual(called_uuids, [str(self.eligible_project.uuid)])

    def test_manager_fallback_when_missing(self, mock_summary):
        self.eligible_project.manager_agent = None
        self.eligible_project.save(update_fields=["manager_agent"])
        mock_summary.return_value = _summary_for_projects(
            [
                {
                    "project_uuid": str(self.eligible_project.uuid),
                    "conversation_count": 0,
                    "resolved_count": 0,
                    "unresolved_count": 0,
                    "human_support_count": 0,
                    "resolution_rate": None,
                    "csat": None,
                    "csat_responses_count": 0,
                    "nps": None,
                    "nps_responses_count": 0,
                }
            ]
        )
        response = self._get({"project_uuids": str(self.eligible_project.uuid)})
        self.assertEqual(response.data["results"][0]["manager"], "2.5")
        self.assertIsNone(response.data["results"][0]["resolution_rate"])
        self.assertIsNone(response.data["average_resolution_rate"])

    def test_include_limits_optional_blocks(self, mock_summary):
        mock_summary.return_value = _summary_for_projects(
            [
                {
                    "project_uuid": str(self.eligible_project.uuid),
                    "conversation_count": 1,
                    "resolved_count": 1,
                    "unresolved_count": 0,
                    "human_support_count": 0,
                    "resolution_rate": 1.0,
                    "csat": 5.0,
                    "csat_responses_count": 1,
                    "nps": 10.0,
                    "nps_responses_count": 1,
                }
            ]
        )
        response = self._get(
            {
                "project_uuids": str(self.eligible_project.uuid),
                "include": "manager,agents",
            }
        )
        row = response.data["results"][0]
        self.assertIn("resolution_rate", row)
        self.assertIn("manager", row)
        self.assertIn("custom_agents_count", row)
        self.assertNotIn("conversation_count", row)
        self.assertNotIn("csat", row)

    def test_pagination_and_sorting(self, mock_summary):
        other = Project.objects.create(
            name="AAA Other",
            org=self.eligible_project.org,
            created_by=self.eligible_project.created_by,
            inline_agent_switch=True,
        )
        mock_summary.return_value = _summary_for_projects(
            [
                {
                    "project_uuid": str(self.eligible_project.uuid),
                    "conversation_count": 5,
                    "resolved_count": 2,
                    "unresolved_count": 0,
                    "human_support_count": 0,
                    "resolution_rate": 0.4,
                    "csat": None,
                    "csat_responses_count": 0,
                    "nps": None,
                    "nps_responses_count": 0,
                },
                {
                    "project_uuid": str(other.uuid),
                    "conversation_count": 10,
                    "resolved_count": 9,
                    "unresolved_count": 0,
                    "human_support_count": 0,
                    "resolution_rate": 0.9,
                    "csat": None,
                    "csat_responses_count": 0,
                    "nps": None,
                    "nps_responses_count": 0,
                },
            ]
        )
        response = self._get(
            {
                "start_date": "2026-05-19",
                "end_date": "2026-05-25",
                "page": 1,
                "page_size": 1,
            }
        )
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["project_uuid"], str(other.uuid))
        # Period average is recomputed from eligible AB2 rows with activity (not mock envelope).
        self.assertEqual(response.data["average_resolution_rate"], 0.65)

    def test_without_project_uuids_does_not_send_all_uuids_to_conversations(self, mock_summary):
        inactive = Project.objects.create(
            name="Inactive AB2",
            org=self.eligible_project.org,
            created_by=self.eligible_project.created_by,
            inline_agent_switch=True,
        )
        mock_summary.return_value = _summary_for_projects(
            [
                {
                    "project_uuid": str(self.eligible_project.uuid),
                    "conversation_count": 3,
                    "resolved_count": 1,
                    "unresolved_count": 1,
                    "human_support_count": 0,
                    "resolution_rate": 0.3333,
                    "csat": None,
                    "csat_responses_count": 0,
                    "nps": None,
                    "nps_responses_count": 0,
                },
                {
                    "project_uuid": str(inactive.uuid),
                    "conversation_count": 0,
                    "resolved_count": 0,
                    "unresolved_count": 0,
                    "human_support_count": 0,
                    "resolution_rate": 0.0,
                    "csat": None,
                    "csat_responses_count": 0,
                    "nps": None,
                    "nps_responses_count": 0,
                },
            ]
        )
        response = self._get(
            {
                "start_date": "2026-05-19",
                "end_date": "2026-05-25",
                "page": 1,
                "page_size": 20,
            }
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_summary.assert_called_once()
        self.assertIsNone(mock_summary.call_args.kwargs["project_uuids"])
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["project_uuid"], str(self.eligible_project.uuid))

    def test_conversations_failure_returns_503(self, mock_summary):
        import requests

        mock_summary.side_effect = requests.ConnectionError("down")
        response = self._get({"project_uuids": str(self.eligible_project.uuid)})
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_conversations_http_502_returns_502(self, mock_summary):
        import requests

        exc = requests.HTTPError("bad gateway")
        exc.response = mock.Mock(status_code=status.HTTP_502_BAD_GATEWAY)
        mock_summary.side_effect = exc
        response = self._get({"project_uuids": str(self.eligible_project.uuid)})
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)

    def test_page_size_over_100_is_truncated_in_response(self, mock_summary):
        mock_summary.return_value = _summary_for_projects(
            [
                {
                    "project_uuid": str(self.eligible_project.uuid),
                    "conversation_count": 1,
                    "resolved_count": 1,
                    "unresolved_count": 0,
                    "human_support_count": 0,
                    "resolution_rate": 1.0,
                    "csat": None,
                    "csat_responses_count": 0,
                    "nps": None,
                    "nps_responses_count": 0,
                }
            ]
        )
        response = self._get(
            {
                "project_uuids": str(self.eligible_project.uuid),
                "page_size": "150",
            }
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["page_size"], 100)

    def test_period_averages_stable_across_pages(self, mock_summary):
        other = Project.objects.create(
            name="ZZZ Other",
            org=self.eligible_project.org,
            created_by=self.eligible_project.created_by,
            inline_agent_switch=True,
        )
        summary = _summary_for_projects(
            [
                {
                    "project_uuid": str(self.eligible_project.uuid),
                    "conversation_count": 1,
                    "resolved_count": 0,
                    "unresolved_count": 1,
                    "human_support_count": 0,
                    "resolution_rate": 0.0,
                    "csat": None,
                    "csat_responses_count": 0,
                    "nps": None,
                    "nps_responses_count": 0,
                },
                {
                    "project_uuid": str(other.uuid),
                    "conversation_count": 1,
                    "resolved_count": 1,
                    "unresolved_count": 0,
                    "human_support_count": 0,
                    "resolution_rate": 1.0,
                    "csat": None,
                    "csat_responses_count": 0,
                    "nps": None,
                    "nps_responses_count": 0,
                },
            ]
        )
        mock_summary.return_value = summary

        query = {
            "start_date": "2026-05-19",
            "end_date": "2026-05-25",
            "page": 1,
            "page_size": 1,
        }
        page_one = self._get(query)
        page_two = self._get({**query, "page": 2})
        self.assertEqual(page_one.status_code, status.HTTP_200_OK)
        self.assertEqual(page_two.status_code, status.HTTP_200_OK)
        self.assertEqual(page_one.data["count"], 2)
        self.assertEqual(page_one.data["average_resolution_rate"], 0.5)
        self.assertEqual(page_two.data["average_resolution_rate"], 0.5)
        self.assertIsNone(page_one.data["average_csat"])
        self.assertIsNone(page_two.data["average_csat"])

    def test_no_visible_projects_returns_empty_payload(self, mock_summary):
        response = self._get({"project_uuids": str(uuid4())})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])
        self.assertIsNone(response.data["average_resolution_rate"])
        self.assertIsNone(response.data["average_csat"])
        mock_summary.assert_not_called()


class TestProjectsResolutionRateServiceHelpers(TestCase):
    def test_parse_calendar_date_accepts_iso_date_string(self):
        self.assertEqual(parse_calendar_date("2026-05-19", "start_date").isoformat(), "2026-05-19")

    def test_parse_page_size_truncates_above_100(self):
        self.assertEqual(parse_page_size("500"), 100)

    def test_parse_page_size_rejects_zero(self):
        with self.assertRaises(ValueError):
            parse_page_size("0")

    def test_resolve_calendar_range_rejects_dates_before_go_live(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_calendar_range(
                parse_calendar_date("2026-03-27", "start_date"),
                parse_calendar_date("2026-05-25", "end_date"),
            )
        self.assertIn(CONVERSATIONS_METRICS_EARLIEST_DATE.isoformat(), str(ctx.exception))

    def test_resolution_rate_from_counts_uses_evaluable_conversations_only(self):
        self.assertIsNone(resolution_rate_from_counts(resolved_count=0, unresolved_count=0))
        self.assertEqual(resolution_rate_from_counts(resolved_count=1, unresolved_count=1), 0.5)
        self.assertEqual(resolution_rate_from_counts(resolved_count=3, unresolved_count=0), 1.0)

    def test_agent_counts_use_only_active_team_integrated_agents(self):
        project = ProjectFactory(inline_agent_switch=True)
        inactive_custom = Agent.objects.create(
            name="Inactive Custom",
            slug="inactive-custom",
            project=project,
            instruction="i",
            collaboration_instructions="c",
            is_official=False,
        )
        Agent.objects.create(
            name="Unassigned Custom",
            slug="unassigned-custom",
            project=project,
            instruction="i",
            collaboration_instructions="c",
            is_official=False,
        )
        active_custom = Agent.objects.create(
            name="Active Custom",
            slug="active-custom",
            project=project,
            instruction="i",
            collaboration_instructions="c",
            is_official=False,
        )
        IntegratedAgent.objects.create(agent=inactive_custom, project=project, is_active=False)
        IntegratedAgent.objects.create(agent=active_custom, project=project, is_active=True)

        catalog_project = ProjectFactory(inline_agent_switch=True, org=project.org, created_by=project.created_by)
        official_agent = Agent.objects.create(
            name="Official",
            slug="official-catalog",
            project=catalog_project,
            instruction="i",
            collaboration_instructions="c",
            is_official=True,
        )
        IntegratedAgent.objects.create(agent=official_agent, project=project, is_active=True)

        counts = _agent_counts([project])[project.uuid]
        self.assertEqual(counts["custom_agents_count"], 1)
        self.assertEqual(counts["official_agents_count"], 1)

    def test_build_result_rows_handles_null_resolution_rate(self):
        project = ProjectFactory(inline_agent_switch=True)
        rows = build_result_rows(
            [project],
            {
                "projects": [
                    {
                        "project_uuid": str(project.uuid),
                        "conversation_count": 2,
                        "resolved_count": 1,
                        "unresolved_count": 1,
                        "human_support_count": 0,
                        "resolution_rate": None,
                        "csat": None,
                        "csat_responses_count": 0,
                        "nps": None,
                        "nps_responses_count": 0,
                    }
                ]
            },
        )
        self.assertEqual(rows[0]["resolution_rate"], 0.5)

    def test_sort_result_rows_orders_by_resolution_rate(self):
        rows = sort_result_rows(
            [
                {"project_name": "B", "resolution_rate": 0.2, "conversation_count": 10},
                {"project_name": "A", "resolution_rate": 0.8, "conversation_count": 1},
                {"project_name": "C", "resolution_rate": 0.8, "conversation_count": 5},
            ]
        )
        self.assertEqual([row["project_name"] for row in rows], ["C", "A", "B"])

    def test_sort_result_rows_puts_null_resolution_rate_last(self):
        rows = sort_result_rows(
            [
                {"project_name": "Null", "resolution_rate": None, "conversation_count": 10},
                {"project_name": "High", "resolution_rate": 0.8, "conversation_count": 1},
                {"project_name": "Low", "resolution_rate": 0.2, "conversation_count": 5},
            ]
        )
        self.assertEqual([row["project_name"] for row in rows], ["High", "Low", "Null"])

    def test_apply_include_blocks_keeps_resolution_rate(self):
        row = apply_include_blocks(
            {
                "project_uuid": "x",
                "project_name": "n",
                "resolution_rate": 0.5,
                "conversation_count": 1,
                "manager": "m",
            },
            {"manager"},
        )
        self.assertEqual(row["resolution_rate"], 0.5)
        self.assertNotIn("conversation_count", row)
