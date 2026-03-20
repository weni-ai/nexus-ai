from unittest import mock
from unittest.mock import patch
from uuid import UUID, uuid4

from django.test import TestCase
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.projects.api.views import EnableHumanSupportView, ProjectUpdateViewset
from nexus.projects.models import Project
from nexus.projects.permissions import has_project_permission
from nexus.usecases.intelligences.tests.intelligence_factory import IntegratedIntelligenceFactory


class TestProjectUpdateViewSet(TestCase):
    def setUp(self):
        integrated_intelligence = IntegratedIntelligenceFactory()
        self.project = integrated_intelligence.project
        self.factory = APIRequestFactory()
        self.view = ProjectUpdateViewset.as_view()
        self.user = self.project.created_by
        self.url = f"/api/{self.project.uuid}/"

    @patch("nexus.usecases.projects.update.update_message")
    def test_update(self, mock_update_message):
        mock_update_message.return_value = None

        request = self.factory.patch(self.url, {"brain_on": True})
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project.uuid)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["brain_on"])
        self.assertTrue(mock_update_message.called)


class TestEnableHumanSupportView(TestCase):
    def setUp(self):
        integrated_intelligence = IntegratedIntelligenceFactory()
        self.project = integrated_intelligence.project
        self.factory = APIRequestFactory()
        self.view = EnableHumanSupportView.as_view()
        self.user = self.project.created_by
        self.project_uuid = str(self.project.uuid)

        # Mock permission check
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

    def test_get_human_support_success(self):
        """Test GET request returns human_support and human_support_prompt"""
        self.project.human_support = True
        self.project.human_support_prompt = "Test prompt"
        self.project.save()

        request = self.factory.get(f"/api/{self.project_uuid}/human-support")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("human_support", response.data)
        self.assertIn("human_support_prompt", response.data)
        self.assertTrue(response.data["human_support"])
        self.assertEqual(response.data["human_support_prompt"], "Test prompt")

    def test_get_human_support_with_false_values(self):
        """Test GET request with human_support=False and empty prompt"""
        self.project.human_support = False
        self.project.human_support_prompt = None
        self.project.save()

        request = self.factory.get(f"/api/{self.project_uuid}/human-support")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["human_support"])
        self.assertIsNone(response.data["human_support_prompt"])

    def test_get_missing_project_uuid(self):
        """Test GET request without project_uuid returns 403 (permission denied)"""
        request = self.factory.get("/api/human-support")
        force_authenticate(request, user=self.user)
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_invalid_uuid_format(self):
        """Test GET request with invalid UUID format returns 400"""

        # Mock permission to raise ValidationError for invalid UUID
        def _permission_with_validation_error(request, project_uuid, method):
            try:
                UUID(project_uuid)
            except (ValueError, TypeError):
                raise ValidationError({"detail": f"An error occurred: ['\"{project_uuid}\" is not a valid UUID.']"})

            project = Project.objects.get(uuid=project_uuid)
            return has_project_permission(request.user, project, method)

        self._mock_ext_permission.side_effect = _permission_with_validation_error

        request = self.factory.get("/api/invalid-uuid/human-support")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid="invalid-uuid")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_get_nonexistent_project(self):
        """Test GET request with non-existent project returns 403 (permission denied)"""
        nonexistent_uuid = str(uuid4())
        request = self.factory.get(f"/api/{nonexistent_uuid}/human-support")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=nonexistent_uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("nexus.usecases.projects.projects_use_case.ProjectsUseCase.update_human_support_config")
    def test_patch_update_human_support_only(self, mock_update_config):
        """Test PATCH request updates only human_support"""
        self.project.human_support = False
        self.project.save()
        mock_update_config.return_value = self.project

        request = self.factory.patch(f"/api/{self.project_uuid}/human-support", {"human_support": True}, format="json")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_update_config.assert_called_once_with(
            project_uuid=self.project_uuid, human_support=True, human_support_prompt=None
        )
        self.assertIn("human_support", response.data)
        self.assertIn("human_support_prompt", response.data)

    @patch("nexus.usecases.projects.projects_use_case.ProjectsUseCase.update_human_support_config")
    def test_patch_update_human_support_prompt_only(self, mock_update_config):
        """Test PATCH request updates only human_support_prompt"""
        new_prompt = "New prompt text"
        self.project.human_support_prompt = None
        self.project.save()
        mock_update_config.return_value = self.project

        request = self.factory.patch(
            f"/api/{self.project_uuid}/human-support", {"human_support_prompt": new_prompt}, format="json"
        )
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_update_config.assert_called_once_with(
            project_uuid=self.project_uuid, human_support=None, human_support_prompt=new_prompt
        )
        self.assertIn("human_support", response.data)
        self.assertIn("human_support_prompt", response.data)

    @patch("nexus.usecases.projects.projects_use_case.ProjectsUseCase.update_human_support_config")
    def test_patch_update_both_fields(self, mock_update_config):
        """Test PATCH request updates both human_support and human_support_prompt"""
        new_prompt = "Updated prompt"
        self.project.human_support = False
        self.project.human_support_prompt = "Old prompt"
        self.project.save()
        mock_update_config.return_value = self.project

        request = self.factory.patch(
            f"/api/{self.project_uuid}/human-support",
            {"human_support": True, "human_support_prompt": new_prompt},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_update_config.assert_called_once_with(
            project_uuid=self.project_uuid, human_support=True, human_support_prompt=new_prompt
        )
        self.assertIn("human_support", response.data)
        self.assertIn("human_support_prompt", response.data)

    def test_patch_missing_project_uuid(self):
        """Test PATCH request without project_uuid returns 403 (permission denied)"""
        request = self.factory.patch("/api/human-support", {"human_support": True}, format="json")
        force_authenticate(request, user=self.user)
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_no_fields_provided(self):
        """Test PATCH request without any fields returns 400"""
        request = self.factory.patch(f"/api/{self.project_uuid}/human-support", {}, format="json")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertIn("At least one of", response.data["error"])

    def test_patch_invalid_human_support_type(self):
        """Test PATCH request with invalid human_support type returns 400"""
        request = self.factory.patch(
            f"/api/{self.project_uuid}/human-support", {"human_support": "not-a-bool"}, format="json"
        )
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertIn("must be a boolean", response.data["error"])

    def test_patch_invalid_human_support_prompt_type(self):
        """Test PATCH request with invalid human_support_prompt type returns 400"""
        request = self.factory.patch(
            f"/api/{self.project_uuid}/human-support", {"human_support_prompt": 123}, format="json"
        )
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)
        self.assertIn("must be a string", response.data["error"])

    def test_patch_invalid_uuid_format(self):
        """Test PATCH request with invalid UUID format returns 400"""

        def _permission_with_validation_error(request, project_uuid, method):
            try:
                UUID(project_uuid)
            except (ValueError, TypeError):
                raise ValidationError({"detail": f"An error occurred: ['\"{project_uuid}\" is not a valid UUID.']"})

            project = Project.objects.get(uuid=project_uuid)
            return has_project_permission(request.user, project, method)

        self._mock_ext_permission.side_effect = _permission_with_validation_error

        request = self.factory.patch("/api/invalid-uuid/human-support", {"human_support": True}, format="json")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid="invalid-uuid")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_patch_nonexistent_project(self):
        """Test PATCH request with non-existent project returns 403 (permission denied)"""
        nonexistent_uuid = str(uuid4())
        request = self.factory.patch(f"/api/{nonexistent_uuid}/human-support", {"human_support": True}, format="json")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=nonexistent_uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
