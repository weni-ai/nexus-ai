from unittest import mock
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.feature_flags.views import FeatureFlagsViewSet
from nexus.projects.models import Project
from nexus.projects.permissions import has_project_permission
from nexus.usecases.intelligences.tests.intelligence_factory import IntegratedIntelligenceFactory


@override_settings(
    GROWTHBOOK_CLIENT_KEY="test",
    GROWTHBOOK_HOST_BASE_URL="https://test.local",
    GROWTHBOOK_WEBHOOK_SECRET="webhook-secret",
)
class TestFeatureFlagsViewSet(TestCase):
    def setUp(self):
        integrated_intelligence = IntegratedIntelligenceFactory()
        self.project = integrated_intelligence.project
        self.user = self.project.created_by
        self.factory = APIRequestFactory()
        self.view = FeatureFlagsViewSet.as_view({"get": "list"})

        self._patcher = mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
        self._mock_ext_permission = self._patcher.start()

        def _local_permission(request, project_uuid, method):
            try:
                project = Project.objects.get(uuid=project_uuid)
                return has_project_permission(request.user, project, method)
            except Project.DoesNotExist:
                return False

        self._mock_ext_permission.side_effect = _local_permission

    def tearDown(self):
        self._patcher.stop()

    @patch("nexus.feature_flags.views.FeatureFlagsService.get_active_feature_flags_for_attributes")
    def test_list_returns_active_features(self, mock_get_active):
        mock_get_active.return_value = ["flag-a", "flag-b"]

        request = self.factory.get(
            "/api/feature_flags/",
            {"project_uuid": str(self.project.uuid)},
        )
        force_authenticate(request, user=self.user)
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["active_features"], ["flag-a", "flag-b"])
        mock_get_active.assert_called_once_with(
            attributes={
                "weni_project": str(self.project.uuid),
                "projectUUID": str(self.project.uuid),
                "userEmail": self.user.email,
            },
        )

    def test_list_requires_authentication(self):
        request = self.factory.get(
            "/api/feature_flags/",
            {"project_uuid": str(self.project.uuid)},
        )
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_requires_project_uuid(self):
        request = self.factory.get("/api/feature_flags/")
        force_authenticate(request, user=self.user)
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_denies_unauthorized_project(self):
        other = IntegratedIntelligenceFactory()
        request = self.factory.get(
            "/api/feature_flags/",
            {"project_uuid": str(other.project.uuid)},
        )
        force_authenticate(request, user=self.user)
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_unknown_project_returns_403(self):
        request = self.factory.get(
            "/api/feature_flags/",
            {"project_uuid": "00000000-0000-0000-0000-000000000099"},
        )
        force_authenticate(request, user=self.user)
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(
    GROWTHBOOK_CLIENT_KEY="test",
    GROWTHBOOK_HOST_BASE_URL="https://test.local",
    GROWTHBOOK_WEBHOOK_SECRET="webhook-secret",
)
class TestFeatureFlagsWebhook(TestCase):
    def setUp(self):
        from django.test.client import RequestFactory
        from weni.feature_flags.views import FeatureFlagsWebhookView

        self.factory = RequestFactory()
        self.view = FeatureFlagsWebhookView.as_view()

    @patch("weni.feature_flags.views.update_feature_flags.delay")
    def test_webhook_triggers_refresh(self, mock_delay):
        request = self.factory.post(
            "/api/growthbook/",
            HTTP_SECRET="webhook-secret",
        )
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        mock_delay.assert_called_once_with(force=True)

    @patch("weni.feature_flags.views.update_feature_flags.delay")
    def test_webhook_rejects_invalid_secret(self, mock_delay):
        request = self.factory.post("/api/growthbook/", HTTP_SECRET="wrong")
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        mock_delay.assert_not_called()
