from unittest import mock

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.projects.api.resolution_criteria_views import (
    AIResolutionCriteriaDetailView,
    AIResolutionCriteriaListCreateView,
    AIResolutionCriteriaValidateView,
)
from nexus.projects.exceptions import ProjectAuthorizationDenied
from nexus.projects.models import Project, ProjectAIResolutionCriterion, ProjectAuthorizationRole
from nexus.projects.permissions import has_project_permission
from nexus.usecases.intelligences.tests.intelligence_factory import IntegratedIntelligenceFactory

BASE_CRITERIA = [
    {"id": "base_resolved", "text": "Mark as resolved when the customer confirms the issue was solved"},
    {"id": "base_unresolved", "text": "Mark as unresolved when the customer is still waiting for a response"},
]


@override_settings(
    AI_RESOLUTION_BASE_CRITERIA=BASE_CRITERIA,
    AI_RESOLUTION_CRITERIA_VALIDATION_NAME="test-validation-lambda",
)
class TestAIResolutionCriteriaViews(TestCase):
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

        self._lambda_patcher = mock.patch("nexus.usecases.projects.ai_resolution_criteria.LambdaUseCase")
        self._mock_lambda_class = self._lambda_patcher.start()
        self._mock_validate = self._mock_lambda_class.return_value.validate_resolution_criterion
        self._mock_validate.return_value = {"valid": True, "rules": []}

    def tearDown(self):
        self._lambda_patcher.stop()
        self._permission_patcher.stop()

    def test_list_returns_base_and_custom_criteria(self):
        criterion = ProjectAIResolutionCriterion.objects.create(
            project=self.project,
            text="Custom criterion",
            created_by=self.user,
        )

        request = self.factory.get(f"/api/{self.project_uuid}/ai-resolution-criteria/")
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaListCreateView.as_view()(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["base_criteria"]), 2)
        self.assertEqual(len(response.data["custom_criteria"]), 1)
        self.assertEqual(response.data["custom_criteria"][0]["id"], str(criterion.uuid))
        self.assertFalse(response.data["base_criteria"][0]["editable"])

    def test_validate_returns_success(self):
        request = self.factory.post(
            f"/api/{self.project_uuid}/ai-validation-criteria/",
            {"text": "Mark as resolved when the customer confirms order delivery", "criterion_id": None},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaValidateView.as_view()(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["validation"]["status"])
        self._mock_validate.assert_called_once_with(
            user_rules=[
                BASE_CRITERIA[0]["text"],
                BASE_CRITERIA[1]["text"],
                "Mark as resolved when the customer confirms order delivery",
            ]
        )

    def test_validate_returns_invalid_error(self):
        self._mock_validate.return_value = {
            "valid": False,
            "rules": [
                {
                    "rule": "Duplicate criterion",
                    "valid": False,
                    "reason": "An equivalent criterion already exists",
                }
            ],
        }

        request = self.factory.post(
            f"/api/{self.project_uuid}/ai-validation-criteria/",
            {"text": "Duplicate criterion"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaValidateView.as_view()(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_CRITERION")
        self.assertEqual(response.data["error"]["message"], "An equivalent criterion already exists")
        self.assertEqual(len(response.data["error"]["rules"]), 1)

    def test_validate_returns_lambda_failure(self):
        from nexus.projects.exceptions import LambdaValidationFailedError

        self._mock_validate.side_effect = LambdaValidationFailedError()

        request = self.factory.post(
            f"/api/{self.project_uuid}/ai-validation-criteria/",
            {"text": "Some criterion"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaValidateView.as_view()(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data["error"]["code"], "LAMBDA_VALIDATION_FAILED")

    def test_create_custom_criterion(self):
        request = self.factory.post(
            f"/api/{self.project_uuid}/ai-resolution-criteria/",
            {"text": "Mark as resolved when the customer confirms order delivery"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaListCreateView.as_view()(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["type"], "custom")
        self.assertTrue(response.data["editable"])
        self._mock_validate.assert_not_called()

    def test_create_rejects_when_custom_limit_reached(self):
        for index in range(10):
            ProjectAIResolutionCriterion.objects.create(
                project=self.project,
                text=f"Custom criterion {index}",
                created_by=self.user,
            )

        request = self.factory.post(
            f"/api/{self.project_uuid}/ai-resolution-criteria/",
            {"text": "Eleventh criterion"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaListCreateView.as_view()(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "CRITERION_LIMIT_REACHED")
        self.assertEqual(ProjectAIResolutionCriterion.objects.filter(project=self.project, is_active=True).count(), 10)

    def test_create_requires_text(self):
        request = self.factory.post(
            f"/api/{self.project_uuid}/ai-resolution-criteria/",
            {"text": "   "},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaListCreateView.as_view()(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "Text is required")

    def test_update_custom_criterion(self):
        criterion = ProjectAIResolutionCriterion.objects.create(
            project=self.project,
            text="Old text",
            created_by=self.user,
        )

        request = self.factory.patch(
            f"/api/{self.project_uuid}/ai-resolution-criteria/{criterion.uuid}/",
            {"text": "Updated text"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaDetailView.as_view()(
            request,
            project_uuid=self.project_uuid,
            criterion_id=str(criterion.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["text"], "Updated text")
        self._mock_validate.assert_not_called()

    def test_update_base_criterion_is_forbidden(self):
        request = self.factory.patch(
            f"/api/{self.project_uuid}/ai-resolution-criteria/base_resolved/",
            {"text": "Updated text"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaDetailView.as_view()(
            request,
            project_uuid=self.project_uuid,
            criterion_id="base_resolved",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["error"]["code"], "UNAUTHORIZED_BASE_CRITERION_CHANGE")

    def test_delete_custom_criterion(self):
        criterion = ProjectAIResolutionCriterion.objects.create(
            project=self.project,
            text="To delete",
            created_by=self.user,
        )

        request = self.factory.delete(
            f"/api/{self.project_uuid}/ai-resolution-criteria/{criterion.uuid}/",
        )
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaDetailView.as_view()(
            request,
            project_uuid=self.project_uuid,
            criterion_id=str(criterion.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        criterion.refresh_from_db()
        self.assertFalse(criterion.is_active)
        self.assertIsNotNone(criterion.deleted_at)

    def test_delete_missing_criterion_returns_404(self):
        request = self.factory.delete(
            f"/api/{self.project_uuid}/ai-resolution-criteria/00000000-0000-0000-0000-000000000000/",
        )
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaDetailView.as_view()(
            request,
            project_uuid=self.project_uuid,
            criterion_id="00000000-0000-0000-0000-000000000000",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "CRITERION_NOT_FOUND")

    def test_list_returns_empty_custom_criteria(self):
        request = self.factory.get(f"/api/{self.project_uuid}/ai-resolution-criteria/")
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaListCreateView.as_view()(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["custom_criteria"], [])

    def test_list_timestamps_use_iso8601_z_format(self):
        ProjectAIResolutionCriterion.objects.create(
            project=self.project,
            text="Custom criterion",
            created_by=self.user,
        )

        request = self.factory.get(f"/api/{self.project_uuid}/ai-resolution-criteria/")
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaListCreateView.as_view()(request, project_uuid=self.project_uuid)

        created_at = response.data["custom_criteria"][0]["created_at"]
        updated_at = response.data["custom_criteria"][0]["updated_at"]
        self.assertRegex(created_at, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertRegex(updated_at, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(created_at, updated_at)

    def test_list_project_not_found(self):
        # ProjectPermission runs before the view; missing project is denied (403), not 404.
        missing_uuid = "00000000-0000-0000-0000-000000000001"
        request = self.factory.get(f"/api/{missing_uuid}/ai-resolution-criteria/")
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaListCreateView.as_view()(request, project_uuid=missing_uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_validate_update_mode_checks_criterion_exists(self):
        criterion = ProjectAIResolutionCriterion.objects.create(
            project=self.project,
            text="Existing criterion",
            created_by=self.user,
        )

        request = self.factory.post(
            f"/api/{self.project_uuid}/ai-validation-criteria/",
            {
                "text": "Updated criterion text",
                "criterion_id": str(criterion.uuid),
            },
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaValidateView.as_view()(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self._mock_validate.assert_called_once_with(
            user_rules=[
                BASE_CRITERIA[0]["text"],
                BASE_CRITERIA[1]["text"],
                "Updated criterion text",
            ]
        )

    def test_validate_includes_other_customs_and_excludes_self_on_update(self):
        kept = ProjectAIResolutionCriterion.objects.create(
            project=self.project,
            text="Keep this custom criterion",
            created_by=self.user,
        )
        editing = ProjectAIResolutionCriterion.objects.create(
            project=self.project,
            text="Old text being replaced",
            created_by=self.user,
        )

        request = self.factory.post(
            f"/api/{self.project_uuid}/ai-validation-criteria/",
            {
                "text": "New candidate text",
                "criterion_id": str(editing.uuid),
            },
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaValidateView.as_view()(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self._mock_validate.assert_called_once_with(
            user_rules=[
                BASE_CRITERIA[0]["text"],
                BASE_CRITERIA[1]["text"],
                kept.text,
                "New candidate text",
            ]
        )

    def test_validate_returns_invalid_error_from_lambda(self):
        self._mock_validate.return_value = {
            "valid": False,
            "rules": [
                {
                    "rule": "Invalid criterion",
                    "valid": False,
                    "reason": "The criterion is invalid",
                }
            ],
        }

        request = self.factory.post(
            f"/api/{self.project_uuid}/ai-validation-criteria/",
            {"text": "Invalid criterion"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaValidateView.as_view()(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_CRITERION")

    def test_viewer_cannot_create_criterion(self):
        from nexus.usecases.users.tests.user_factory import UserFactory

        viewer = UserFactory()
        self.project.authorizations.update_or_create(
            user=viewer,
            defaults={"role": ProjectAuthorizationRole.VIEWER.value},
        )

        request = self.factory.post(
            f"/api/{self.project_uuid}/ai-resolution-criteria/",
            {"text": "Viewer attempt"},
            format="json",
        )
        force_authenticate(request, user=viewer)
        response = AIResolutionCriteriaListCreateView.as_view()(request, project_uuid=self.project_uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_invalid_uuid_returns_404(self):
        request = self.factory.patch(
            f"/api/{self.project_uuid}/ai-resolution-criteria/not-a-uuid/",
            {"text": "Updated text"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        response = AIResolutionCriteriaDetailView.as_view()(
            request,
            project_uuid=self.project_uuid,
            criterion_id="not-a-uuid",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "CRITERION_NOT_FOUND")
