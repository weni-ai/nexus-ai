from unittest import mock

from django.test import override_settings
from rest_framework import status
from rest_framework.test import force_authenticate

from nexus.projects.api.tests.test_conversations_proxy_permissions import _PermissionTestBase
from nexus.projects.api.views import FlowsDbCohortReconcileJobView, FlowsDbCohortReconcileProxyView
from nexus.projects.services.flows_db_cohort_job_store import (
    STATUS_COMPLETED,
    STATUS_QUEUED,
    create_job,
    get_job,
)


@mock.patch("nexus.projects.tasks.reconcile_flows_db_cohort_email_task.apply_async")
@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class TestFlowsDbCohortReconcileProxyView(_PermissionTestBase):
    def setUp(self):
        super().setUp()
        self.view = FlowsDbCohortReconcileProxyView.as_view()
        self.url = f"/api/v2/{self.project_uuid}/flows-db-cohort"

    @mock.patch("nexus.projects.services.flows_db_cohort_credentials.store_flows_api_token")
    def test_project_permission_queues_local_task(self, mock_store_token, mock_apply_async):
        mock_apply_async.return_value = mock.Mock()

        request = self.factory.post(
            self.url,
            {
                "flows_api_token": "secret",
                "date_start": "2026-01-10T00:00:00Z",
                "date_end": "2026-01-10T23:59:59Z",
            },
            format="json",
        )
        force_authenticate(request, user=self.authorized_user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        task_id = mock_apply_async.call_args.kwargs["task_id"]
        self.assertEqual(response.data["job_id"], task_id)
        self.assertEqual(response.data["delivery"], "email")
        self.assertEqual(response.data["recipient_email"], self.authorized_user.email)
        mock_apply_async.assert_called_once()
        cfg, recipient, delivery = mock_apply_async.call_args.kwargs["args"]
        self.assertEqual(recipient, self.authorized_user.email)
        self.assertEqual(delivery, "email")
        self.assertEqual(cfg["project"], str(self.project_uuid))
        self.assertNotIn("flows_api_token", cfg)
        mock_store_token.assert_called_once_with(task_id, "secret", timeout=3900)  # TASK_TIME_LIMIT 3600 + 300

        job = get_job(task_id)
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], STATUS_QUEUED)
        self.assertEqual(job["delivery"], "email")

    @mock.patch("nexus.projects.services.flows_db_cohort_service.run_flows_db_cohort_reconcile_range")
    def test_json_delivery_returns_sync_report(self, mock_run_sync, mock_apply_async):
        report = {"overall_status": "aligned", "day_summaries": []}
        mock_run_sync.return_value = report

        request = self.factory.post(
            self.url,
            {
                "flows_api_token": "secret",
                "delivery": "json",
                "date_start": "2026-01-10T00:00:00Z",
                "date_end": "2026-01-10T23:59:59Z",
            },
            format="json",
        )
        force_authenticate(request, user=self.authorized_user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "completed")
        self.assertEqual(response.data["delivery"], "json")
        self.assertEqual(response.data["report"], report)
        mock_apply_async.assert_not_called()
        mock_run_sync.assert_called_once()

    def test_json_delivery_rejects_multi_day_range(self, mock_apply_async):
        request = self.factory.post(
            self.url,
            {
                "flows_api_token": "secret",
                "delivery": "json",
                "date_start": "2026-01-10T00:00:00Z",
                "date_end": "2026-01-11T23:59:59Z",
            },
            format="json",
        )
        force_authenticate(request, user=self.authorized_user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_apply_async.assert_not_called()

    def test_internal_permission_grants_access_when_project_denied(self, mock_apply_async):
        mock_apply_async.return_value = mock.Mock(id="celery-job-internal")

        request = self.factory.post(
            self.url,
            {
                "flows_api_token": "secret",
                "date_start": "2026-01-10T00:00:00Z",
                "date_end": "2026-01-10T23:59:59Z",
            },
            format="json",
        )
        force_authenticate(request, user=self.internal_user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        mock_apply_async.assert_called_once()

    def test_no_permission_returns_403(self, mock_apply_async):
        request = self.factory.post(
            self.url,
            {
                "flows_api_token": "secret",
                "date_start": "2026-01-10T00:00:00Z",
                "date_end": "2026-01-10T23:59:59Z",
            },
            format="json",
        )
        force_authenticate(request, user=self.unauthorized_user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_apply_async.assert_not_called()

    def test_unauthenticated_returns_401(self, mock_apply_async):
        request = self.factory.post(
            self.url,
            {
                "flows_api_token": "secret",
                "date_start": "2026-01-10T00:00:00Z",
                "date_end": "2026-01-10T23:59:59Z",
            },
            format="json",
        )
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        mock_apply_async.assert_not_called()

    def test_user_without_email_returns_400_for_email_delivery(self, mock_apply_async):
        request = self.factory.post(
            self.url,
            {
                "flows_api_token": "secret",
                "date_start": "2026-01-10T00:00:00Z",
                "date_end": "2026-01-10T23:59:59Z",
            },
            format="json",
        )
        user = self.authorized_user
        user.email = ""
        force_authenticate(request, user=user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_apply_async.assert_not_called()


class TestFlowsDbCohortReconcileJobView(_PermissionTestBase):
    def setUp(self):
        super().setUp()
        self.view = FlowsDbCohortReconcileJobView.as_view()
        self.job_id = "job-123"
        self.url = f"/api/v2/{self.project_uuid}/flows-db-cohort/{self.job_id}"

    def test_returns_completed_job_report(self):
        create_job(
            self.job_id,
            project_id=self.project_uuid,
            delivery="email",
            requested_range={
                "from_inclusive": "2026-01-10T00:00:00Z",
                "to_inclusive": "2026-01-10T23:59:59Z",
            },
        )
        from nexus.projects.services.flows_db_cohort_job_store import set_job_completed

        report = {"overall_status": "aligned", "day_summaries": []}
        set_job_completed(self.job_id, report)

        request = self.factory.get(self.url)
        force_authenticate(request, user=self.authorized_user)
        response = self.view(request, project_uuid=self.project_uuid, job_id=self.job_id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], STATUS_COMPLETED)
        self.assertEqual(response.data["report"], report)

    def test_job_not_found_returns_404(self):
        request = self.factory.get(self.url)
        force_authenticate(request, user=self.authorized_user)
        response = self.view(request, project_uuid=self.project_uuid, job_id="missing")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_wrong_project_returns_404(self):
        create_job(
            self.job_id,
            project_id=self.project_uuid,
            delivery="email",
            requested_range={
                "from_inclusive": "2026-01-10T00:00:00Z",
                "to_inclusive": "2026-01-10T23:59:59Z",
            },
        )

        other_project = str(self.project_uuid).replace("a", "b", 1)
        request = self.factory.get(self.url)
        force_authenticate(request, user=self.authorized_user)
        response = self.view(request, project_uuid=other_project, job_id=self.job_id)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_no_permission_returns_403(self):
        create_job(
            self.job_id,
            project_id=self.project_uuid,
            delivery="email",
            requested_range={
                "from_inclusive": "2026-01-10T00:00:00Z",
                "to_inclusive": "2026-01-10T23:59:59Z",
            },
        )

        request = self.factory.get(self.url)
        force_authenticate(request, user=self.unauthorized_user)
        response = self.view(request, project_uuid=self.project_uuid, job_id=self.job_id)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
