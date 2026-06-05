from unittest import mock

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.projects.api.views import ConversationsProxyView
from nexus.projects.models import Project
from nexus.projects.permissions import has_project_permission
from nexus.usecases.intelligences.tests.intelligence_factory import IntegratedIntelligenceFactory

CONVERSATIONS_LIST_RESPONSE = {
    "total_count": 0,
    "next": None,
    "previous": None,
    "results": [],
    "status_summary": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0},
}


def _build_requests_response(json_data, status_code=200):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


@mock.patch("nexus.projects.api.views.requests.get")
class TestConversationsProxyTopicsPassthrough(TestCase):
    def setUp(self):
        integrated = IntegratedIntelligenceFactory()
        self.project = integrated.project
        self.project_uuid = str(self.project.uuid)
        self.user = self.project.created_by
        self.factory = APIRequestFactory()
        self.view = ConversationsProxyView.as_view()
        self.url = f"/api/v2/{self.project_uuid}/conversations"

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

    def test_topics_query_param_is_forwarded_to_conversations_service(self, mock_get):
        mock_get.return_value = _build_requests_response(CONVERSATIONS_LIST_RESPONSE)

        request = self.factory.get(f"{self.url}?topics=Atendimento,unclassified")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["topics"], "Atendimento,unclassified")
