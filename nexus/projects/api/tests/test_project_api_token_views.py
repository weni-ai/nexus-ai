from unittest import mock

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.projects.api.project_api_token_views import ProjectApiTokenCreateView
from nexus.projects.exceptions import ProjectAuthorizationDenied
from nexus.projects.models import Project, ProjectApiToken, ProjectAuthorizationRole
from nexus.projects.permissions import has_project_permission
from nexus.usecases.intelligences.tests.intelligence_factory import IntegratedIntelligenceFactory
from nexus.usecases.projects.project_api_token import ProjectApiTokenUseCase


class TestProjectApiTokenCreateView(TestCase):
    def setUp(self):
        integrated_intelligence = IntegratedIntelligenceFactory()
        self.project = integrated_intelligence.project
        self.user = self.project.created_by
        self.project.authorizations.update_or_create(
            user=self.user,
            defaults={"role": ProjectAuthorizationRole.MODERATOR.value},
        )
        self.factory = APIRequestFactory()
        self.project_uuid = str(self.project.uuid)

        self._permission_patcher = mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
        self._mock_ext_permission = self._permission_patcher.start()

        def _local_permission(request, project_uuid, method):
            try:
                project = Project.objects.get(uuid=project_uuid)
                return has_project_permission(request.user, project, method)
            except Project.DoesNotExist:
                return False
            except ProjectAuthorizationDenied:
                return False

        self._mock_ext_permission.side_effect = _local_permission

    def tearDown(self):
        self._permission_patcher.stop()

    def test_create_token_returns_plaintext_once(self):
        request = self.factory.post(
            f"/api/{self.project_uuid}/api-tokens/",
            {"name": "public-supervisor"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = ProjectApiTokenCreateView.as_view()(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "public-supervisor")
        self.assertEqual(response.data["scope"], ProjectApiTokenUseCase.DEFAULT_SCOPE)
        self.assertTrue(response.data["enabled"])
        self.assertIn("token", response.data)
        self.assertNotIn("token_hash", response.data)
        self.assertNotIn("salt", response.data)

        api_token = ProjectApiToken.objects.get(id=response.data["id"])
        self.assertTrue(api_token.matches(response.data["token"]))
        self.assertEqual(api_token.created_by, self.user)

    def test_create_token_without_name_uses_auto_name(self):
        request = self.factory.post(
            f"/api/{self.project_uuid}/api-tokens/",
            {},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = ProjectApiTokenCreateView.as_view()(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["name"].startswith("Auto "))

    def test_create_token_duplicate_name_returns_conflict(self):
        ProjectApiTokenUseCase().create_token(
            project=self.project,
            name="duplicate",
            created_by=self.user,
        )

        request = self.factory.post(
            f"/api/{self.project_uuid}/api-tokens/",
            {"name": "duplicate"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = ProjectApiTokenCreateView.as_view()(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("error", response.data)

    def test_create_token_project_not_found(self):
        missing_uuid = "00000000-0000-0000-0000-000000000000"
        request = self.factory.post(
            f"/api/{missing_uuid}/api-tokens/",
            {"name": "missing-project"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        # Permission is checked first; mock it to allow so we exercise 404 from use case
        self._mock_ext_permission.return_value = True
        self._mock_ext_permission.side_effect = None

        response = ProjectApiTokenCreateView.as_view()(request, project_uuid=missing_uuid)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_token_forbidden_without_permission(self):
        self._mock_ext_permission.side_effect = None
        self._mock_ext_permission.return_value = False

        request = self.factory.post(
            f"/api/{self.project_uuid}/api-tokens/",
            {"name": "no-access"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = ProjectApiTokenCreateView.as_view()(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
