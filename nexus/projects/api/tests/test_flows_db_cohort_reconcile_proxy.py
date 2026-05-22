from unittest import mock
from uuid import uuid4

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.projects.api.views import FlowsDbCohortReconcileProxyView
from nexus.projects.models import Project
from nexus.projects.permissions import has_project_permission
from nexus.usecases.intelligences.tests.intelligence_factory import IntegratedIntelligenceFactory
from nexus.usecases.users.tests.user_factory import UserFactory

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


class TestFlowsDbCohortReconcileProxyView(TestCase):
    def setUp(self):
        integrated = IntegratedIntelligenceFactory()
        self.project = integrated.project
        self.project_uuid = str(self.project.uuid)
        self.authorized_user = self.project.created_by
        self.unauthorized_user = UserFactory()
        self.factory = APIRequestFactory()
        self.view = FlowsDbCohortReconcileProxyView.as_view()
        self.url = f"/api/v2/{self.project_uuid}/flows-db-cohort"

        self._patcher = mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
        self._mock_ext_perm = self._patcher.start()

        def _local_permission(request, project_uuid, method):
            try:
                project = Project.objects.get(uuid=project_uuid)
                return has_project_permission(request.user, project, method)
            except Project.DoesNotExist:
                return False

        self._mock_ext_perm.side_effect = _local_permission

    def tearDown(self):
        self._patcher.stop()

    @mock.patch("nexus.internals.conversations.ConversationsRESTClient.post_flows_db_cohort_reconcile")
    def test_injects_recipient_email_from_user(self, mock_post):
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

        assert response.status_code == status.HTTP_202_ACCEPTED
        mock_post.assert_called_once()
        _project_uuid, payload = mock_post.call_args[0]
        assert payload["recipient_email"] == self.authorized_user.email
        assert "flows_api_token" in payload

    @mock.patch("nexus.internals.conversations.ConversationsRESTClient.post_flows_db_cohort_reconcile")
    def test_forbidden_without_project_permission(self, mock_post):
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

        assert response.status_code == status.HTTP_403_FORBIDDEN
        mock_post.assert_not_called()
