from unittest import mock
from uuid import uuid4

from rest_framework import status
from rest_framework.test import force_authenticate

from nexus.projects.api.tests.test_conversations_proxy_permissions import _PermissionTestBase
from nexus.projects.api.views import FlowsDbCohortReconcileProxyView

QUEUED_RESPONSE = {
    "status": "queued",
    "job_id": "celery-job-abc",
    "project_id": str(uuid4()),
    "recipient_email": "owner@example.com",
    "requested_range": {
        "from_inclusive": "2026-01-10T00:00:00Z",
        "to_inclusive": "2026-01-10T23:59:59Z",
    },
}


def _build_post_response(json_data, status_code=202):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = ""
    resp.reason = "Accepted"
    resp.raise_for_status.return_value = None
    return resp


@mock.patch("nexus.internals.conversations.ConversationsRESTClient.post_flows_db_cohort_reconcile")
class TestFlowsDbCohortReconcileProxyView(_PermissionTestBase):
    def setUp(self):
        super().setUp()
        self.view = FlowsDbCohortReconcileProxyView.as_view()
        self.url = f"/api/v2/{self.project_uuid}/flows-db-cohort"

    def test_project_permission_grants_access(self, mock_post):
        mock_post.return_value = _build_post_response({**QUEUED_RESPONSE, "project_id": self.project_uuid})

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
        mock_post.assert_called_once()
        _project_uuid, payload = mock_post.call_args[0]
        self.assertEqual(payload["recipient_email"], self.authorized_user.email)
        self.assertIn("flows_api_token", payload)

    def test_internal_permission_grants_access_when_project_denied(self, mock_post):
        mock_post.return_value = _build_post_response({**QUEUED_RESPONSE, "project_id": self.project_uuid})

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
        mock_post.assert_called_once()
        _project_uuid, payload = mock_post.call_args[0]
        self.assertEqual(payload["recipient_email"], self.internal_user.email)

    def test_no_permission_returns_403(self, mock_post):
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
        mock_post.assert_not_called()

    def test_unauthenticated_returns_401(self, mock_post):
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
        mock_post.assert_not_called()
