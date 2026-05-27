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
from nexus.inline_agents.models import Agent
from nexus.projects.api.resolution_rate_views import ProjectsResolutionRateView
from nexus.projects.models import Project
from nexus.projects.services.projects_resolution_rate import (
    apply_include_blocks,
    build_result_rows,
    parse_page_size,
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
        self.ab2_project = integrated.project
        self.ab2_project.agents_backend = "BedrockBackend"
        self.ab2_project.save(update_fields=["agents_backend"])

        self.ab25_project = Project.objects.create(
            name="AB 2.5 Project",
            org=self.ab2_project.org,
            created_by=self.ab2_project.created_by,
            agents_backend="OpenAIBackend",
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
        self.ab2_project.manager_agent = self.manager
        self.ab2_project.use_components = True
        self.ab2_project.save(update_fields=["manager_agent", "use_components"])

        Agent.objects.create(
            name="Official",
            slug="official-agent",
            project=self.ab2_project,
            instruction="i",
            collaboration_instructions="c",
            is_official=True,
        )
        Agent.objects.create(
            name="Custom",
            slug="custom-agent",
            project=self.ab2_project,
            instruction="i",
            collaboration_instructions="c",
            is_official=False,
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

    def test_invalid_page_size_returns_400(self, mock_summary):
        response = self._get({"project_uuids": str(self.ab2_project.uuid), "page_size": "0"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        assert "page_size" in response.data
        mock_summary.assert_not_called()

    def test_client_called_with_single_batch_not_per_project(self, mock_summary):
        other = Project.objects.create(
            name="Batch Other",
            org=self.ab2_project.org,
            created_by=self.ab2_project.created_by,
            agents_backend="BedrockBackend",
        )
        mock_summary.return_value = _summary_for_projects([])
        self._get(
            {
                "project_uuids": f"{self.ab2_project.uuid},{other.uuid}",
                "start_date": "2026-05-19",
                "end_date": "2026-05-25",
            }
        )
        mock_summary.assert_called_once()
        called_uuids = set(mock_summary.call_args.kwargs["project_uuids"])
        self.assertEqual(
            called_uuids,
            {str(self.ab2_project.uuid), str(other.uuid)},
        )

    def test_success_merges_conversations_and_local_metadata(self, mock_summary):
        mock_summary.return_value = _summary_for_projects(
            [
                {
                    "project_uuid": str(self.ab2_project.uuid),
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
                "project_uuids": str(self.ab2_project.uuid),
                "start_date": "2026-05-19",
                "end_date": "2026-05-25",
            }
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.data["results"][0]
        self.assertEqual(row["project_name"], self.ab2_project.name)
        self.assertEqual(row["manager"], "Manager X")
        self.assertTrue(row["uses_components"])
        self.assertEqual(row["agents_count"], 2)
        self.assertEqual(row["official_agents_count"], 1)
        self.assertEqual(row["conversation_count"], 10)
        self.assertEqual(response.data["average_resolution_rate"], 0.5)
        mock_summary.assert_called_once()

    def test_filters_only_ab2_projects(self, mock_summary):
        mock_summary.return_value = _summary_for_projects(
            [
                {
                    "project_uuid": str(self.ab2_project.uuid),
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
                "project_uuids": f"{self.ab2_project.uuid},{self.ab25_project.uuid}",
                "start_date": "2026-05-19",
                "end_date": "2026-05-25",
            }
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        called_uuids = mock_summary.call_args.kwargs["project_uuids"]
        self.assertEqual(called_uuids, [str(self.ab2_project.uuid)])

    def test_manager_fallback_when_missing(self, mock_summary):
        self.ab2_project.manager_agent = None
        self.ab2_project.save(update_fields=["manager_agent"])
        mock_summary.return_value = _summary_for_projects(
            [
                {
                    "project_uuid": str(self.ab2_project.uuid),
                    "conversation_count": 0,
                    "resolved_count": 0,
                    "unresolved_count": 0,
                    "human_support_count": 0,
                    "resolution_rate": 0.0,
                    "csat": None,
                    "csat_responses_count": 0,
                    "nps": None,
                    "nps_responses_count": 0,
                }
            ]
        )
        response = self._get({"project_uuids": str(self.ab2_project.uuid)})
        self.assertEqual(response.data["results"][0]["manager"], "2.5")

    def test_include_limits_optional_blocks(self, mock_summary):
        mock_summary.return_value = _summary_for_projects(
            [
                {
                    "project_uuid": str(self.ab2_project.uuid),
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
                "project_uuids": str(self.ab2_project.uuid),
                "include": "manager,agents",
            }
        )
        row = response.data["results"][0]
        self.assertIn("resolution_rate", row)
        self.assertIn("manager", row)
        self.assertIn("agents_count", row)
        self.assertNotIn("conversation_count", row)
        self.assertNotIn("csat", row)

    def test_pagination_and_sorting(self, mock_summary):
        other = Project.objects.create(
            name="AAA Other",
            org=self.ab2_project.org,
            created_by=self.ab2_project.created_by,
            agents_backend="BedrockBackend",
        )
        mock_summary.return_value = _summary_for_projects(
            [
                {
                    "project_uuid": str(self.ab2_project.uuid),
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
        response = self._get({"page": 1, "page_size": 1})
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["project_uuid"], str(other.uuid))
        self.assertEqual(response.data["average_resolution_rate"], 0.5)

    def test_conversations_failure_returns_503(self, mock_summary):
        import requests

        mock_summary.side_effect = requests.ConnectionError("down")
        response = self._get({"project_uuids": str(self.ab2_project.uuid)})
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_conversations_http_502_returns_502(self, mock_summary):
        import requests

        exc = requests.HTTPError("bad gateway")
        exc.response = mock.Mock(status_code=status.HTTP_502_BAD_GATEWAY)
        mock_summary.side_effect = exc
        response = self._get({"project_uuids": str(self.ab2_project.uuid)})
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)

    def test_page_size_over_100_is_truncated_in_response(self, mock_summary):
        mock_summary.return_value = _summary_for_projects(
            [
                {
                    "project_uuid": str(self.ab2_project.uuid),
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
                "project_uuids": str(self.ab2_project.uuid),
                "page_size": "150",
            }
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["page_size"], 100)

    def test_period_averages_stable_across_pages(self, mock_summary):
        other = Project.objects.create(
            name="ZZZ Other",
            org=self.ab2_project.org,
            created_by=self.ab2_project.created_by,
            agents_backend="BedrockBackend",
        )
        summary = _summary_for_projects(
            [
                {
                    "project_uuid": str(self.ab2_project.uuid),
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
        summary["average_resolution_rate"] = 0.5
        summary["average_csat"] = 4.0
        summary["average_nps"] = 8.0
        mock_summary.return_value = summary

        page_one = self._get({"page": 1, "page_size": 1})
        page_two = self._get({"page": 2, "page_size": 1})
        self.assertEqual(page_one.status_code, status.HTTP_200_OK)
        self.assertEqual(page_two.status_code, status.HTTP_200_OK)
        self.assertEqual(page_one.data["count"], 2)
        self.assertEqual(page_one.data["average_resolution_rate"], 0.5)
        self.assertEqual(page_two.data["average_resolution_rate"], 0.5)
        self.assertEqual(page_one.data["average_csat"], 4.0)
        self.assertEqual(page_two.data["average_csat"], 4.0)

    def test_no_visible_projects_returns_empty_payload(self, mock_summary):
        response = self._get({"project_uuids": str(uuid4())})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])
        self.assertEqual(response.data["average_resolution_rate"], 0.0)
        self.assertIsNone(response.data["average_csat"])
        mock_summary.assert_not_called()


class TestProjectsResolutionRateServiceHelpers(TestCase):
    def test_parse_page_size_truncates_above_100(self):
        self.assertEqual(parse_page_size("500"), 100)

    def test_parse_page_size_rejects_zero(self):
        with self.assertRaises(ValueError):
            parse_page_size("0")

    def test_build_result_rows_handles_null_resolution_rate(self):
        project = ProjectFactory(agents_backend="BedrockBackend")
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
