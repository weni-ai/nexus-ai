from unittest import mock
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.projects.api.views import ConversationDetailProxyView, ConversationsProxyView
from nexus.projects.models import Project
from nexus.projects.permissions import has_project_permission
from nexus.usecases.intelligences.tests.intelligence_factory import IntegratedIntelligenceFactory
from nexus.usecases.users.tests.user_factory import UserFactory

CONVERSATIONS_LIST_RESPONSE = {
    "count": 1,
    "next": None,
    "previous": None,
    "results": [
        {
            "uuid": str(uuid4()),
            "created_at": "2026-01-01T00:00:00Z",
            "end_date": None,
            "status": "open",
            "contact_urn": "tel:+5511999999999",
            "channel_uuid": str(uuid4()),
        }
    ],
}

CONVERSATION_DETAIL_RESPONSE = {
    "uuid": str(uuid4()),
    "created_at": "2026-01-01T00:00:00Z",
    "end_date": None,
    "status": "open",
    "contact_urn": "tel:+5511999999999",
    "channel_uuid": str(uuid4()),
    "classification": {"topic": "general"},
    "messages": {"next": None, "previous": None, "results": []},
}


def _build_requests_response(json_data, status_code=200):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


class _PermissionTestBase(TestCase):
    """Shared setUp for both proxy view test classes."""

    def setUp(self):
        integrated = IntegratedIntelligenceFactory()
        self.project = integrated.project
        self.project_uuid = str(self.project.uuid)

        self.authorized_user = self.project.created_by
        self.unauthorized_user = UserFactory()
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


@mock.patch("nexus.projects.api.views.requests.get")
class TestConversationsProxyViewPermissions(_PermissionTestBase):
    def setUp(self):
        super().setUp()
        self.view = ConversationsProxyView.as_view()
        self.url = f"/api/v2/{self.project_uuid}/conversations"

    def test_project_permission_grants_access(self, mock_get):
        mock_get.return_value = _build_requests_response(CONVERSATIONS_LIST_RESPONSE)

        request = self.factory.get(self.url)
        force_authenticate(request, user=self.authorized_user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_get.assert_called_once()

    def test_internal_permission_grants_access_when_project_denied(self, mock_get):
        mock_get.return_value = _build_requests_response(CONVERSATIONS_LIST_RESPONSE)

        request = self.factory.get(self.url)
        force_authenticate(request, user=self.internal_user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_get.assert_called_once()

    def test_no_permission_returns_403(self, mock_get):
        request = self.factory.get(self.url)
        force_authenticate(request, user=self.unauthorized_user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_get.assert_not_called()

    def test_unauthenticated_returns_401(self, mock_get):
        request = self.factory.get(self.url)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        mock_get.assert_not_called()


@mock.patch("nexus.projects.api.views.requests.get")
class TestConversationDetailProxyViewPermissions(_PermissionTestBase):
    def setUp(self):
        super().setUp()
        self.view = ConversationDetailProxyView.as_view()
        self.conversation_uuid = str(uuid4())
        self.url = f"/api/v2/{self.project_uuid}/conversations/{self.conversation_uuid}"

    def test_project_permission_grants_access(self, mock_get):
        mock_get.return_value = _build_requests_response(CONVERSATION_DETAIL_RESPONSE)

        request = self.factory.get(self.url)
        force_authenticate(request, user=self.authorized_user)
        response = self.view(request, project_uuid=self.project_uuid, conversation_uuid=self.conversation_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_get.assert_called_once()

    def test_internal_permission_grants_access_when_project_denied(self, mock_get):
        mock_get.return_value = _build_requests_response(CONVERSATION_DETAIL_RESPONSE)

        request = self.factory.get(self.url)
        force_authenticate(request, user=self.internal_user)
        response = self.view(request, project_uuid=self.project_uuid, conversation_uuid=self.conversation_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_get.assert_called_once()

    def test_no_permission_returns_403(self, mock_get):
        request = self.factory.get(self.url)
        force_authenticate(request, user=self.unauthorized_user)
        response = self.view(request, project_uuid=self.project_uuid, conversation_uuid=self.conversation_uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_get.assert_not_called()

    def test_unauthenticated_returns_401(self, mock_get):
        request = self.factory.get(self.url)
        response = self.view(request, project_uuid=self.project_uuid, conversation_uuid=self.conversation_uuid)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        mock_get.assert_not_called()
