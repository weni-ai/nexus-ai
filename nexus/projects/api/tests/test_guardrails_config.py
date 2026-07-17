from datetime import datetime, timezone
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone as django_timezone
from rest_framework import status
from rest_framework.test import APIClient

from nexus.projects.models import Project, ProjectAuthorizationRole, ProjectGuardrailsConfig
from nexus.projects.permissions import has_project_permission
from nexus.usecases.guardrails.project_guardrails_config import ProjectGuardrailsConfigUseCase
from nexus.usecases.projects.tests.project_factory import ProjectAuthFactory, ProjectFactory
from nexus.usecases.users.tests.user_factory import UserFactory


@override_settings(GUARDRAILS_CONFIG_FEATURE_DEPLOY_AT=datetime(2026, 7, 1, tzinfo=timezone.utc))
class ProjectGuardrailsConfigAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.project = ProjectFactory()
        self.project.created_at = django_timezone.make_aware(datetime(2026, 8, 1))
        self.project.save(update_fields=["created_at"])
        self.user = self.project.created_by
        self.url = reverse("project-guardrails-config", kwargs={"project_uuid": str(self.project.uuid)})

        self._patcher = mock.patch("nexus.projects.api.permissions.has_external_general_project_permission")
        self._mock_ext_permission = self._patcher.start()

        def _local_permission(request, project_uuid, method):
            try:
                project = Project.objects.get(uuid=project_uuid)
                return has_project_permission(request.user, project, method)
            except Project.DoesNotExist:
                return False

        self._mock_ext_permission.side_effect = _local_permission
        self.client.force_authenticate(user=self.user)

    def tearDown(self):
        self._patcher.stop()

    def test_get_lazy_init_new_project_blocks_all(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["writable"])
        self.assertFalse(response.data["blocking_message_is_custom"])
        self.assertTrue(response.data["blocking_message"])
        self.assertEqual(len(response.data["categories"]), len(ProjectGuardrailsConfigUseCase.catalog_slugs()))
        self.assertTrue(all(category["blocked"] for category in response.data["categories"]))
        self.assertTrue(ProjectGuardrailsConfig.objects.filter(project=self.project).exists())

    def test_get_lazy_init_existing_project_unblocks_all(self):
        existing = ProjectFactory()
        existing.created_at = django_timezone.make_aware(datetime(2025, 1, 1))
        existing.save(update_fields=["created_at"])
        self.client.force_authenticate(user=existing.created_by)
        url = reverse("project-guardrails-config", kwargs={"project_uuid": str(existing.uuid)})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(any(category["blocked"] for category in response.data["categories"]))

    def test_patch_block_category_without_confirmation(self):
        ProjectGuardrailsConfigUseCase.get_or_initialize(self.project)
        ProjectGuardrailsConfig.objects.filter(project=self.project).update(
            category_states=ProjectGuardrailsConfigUseCase.build_default_category_states(blocked=False),
        )

        response = self.client.patch(
            self.url,
            {"category_states": {"politics": True}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        politics = next(item for item in response.data["categories"] if item["slug"] == "politics")
        self.assertTrue(politics["blocked"])

    def test_patch_unblock_without_confirm_returns_409(self):
        ProjectGuardrailsConfigUseCase.get_or_initialize(self.project)

        response = self.client.patch(
            self.url,
            {"category_states": {"politics": False}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(response.data["requires_confirmation"])
        self.assertEqual(response.data["confirmation_type"], "disable_category")

    def test_patch_unblock_with_confirm_persists(self):
        ProjectGuardrailsConfigUseCase.get_or_initialize(self.project)

        response = self.client.patch(
            self.url,
            {"category_states": {"politics": False}, "confirm_disable": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        politics = next(item for item in response.data["categories"] if item["slug"] == "politics")
        self.assertFalse(politics["blocked"])

    def test_patch_unblock_all_requires_disable_all_confirmation(self):
        config = ProjectGuardrailsConfigUseCase.get_or_initialize(self.project)
        all_unblocked = ProjectGuardrailsConfigUseCase.build_default_category_states(blocked=False)

        response = self.client.patch(
            self.url,
            {"category_states": all_unblocked},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["confirmation_type"], "disable_all")

        confirmed = self.client.patch(
            self.url,
            {"category_states": all_unblocked, "confirm_disable": True},
            format="json",
        )
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK)
        config.refresh_from_db()
        self.assertFalse(any(config.category_states.values()))

    def test_patch_blocking_message_success(self):
        ProjectGuardrailsConfigUseCase.get_or_initialize(self.project)

        response = self.client.patch(
            self.url,
            {"blocking_message": "Custom refusal message"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["blocking_message_is_custom"])
        self.assertEqual(response.data["blocking_message"], "Custom refusal message")

    def test_patch_blocking_message_over_limit_returns_400(self):
        ProjectGuardrailsConfigUseCase.get_or_initialize(self.project)
        too_long = "x" * (ProjectGuardrailsConfig.BLOCKING_MESSAGE_MAX_LENGTH + 1)

        response = self.client.patch(
            self.url,
            {"blocking_message": too_long},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_denied_for_contributor(self):
        contributor = UserFactory()
        ProjectAuthFactory(
            project=self.project,
            user=contributor,
            role=ProjectAuthorizationRole.CONTRIBUTOR.value,
        )
        self.client.force_authenticate(user=contributor)

        response = self.client.patch(
            self.url,
            {"category_states": {"politics": True}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_writable_false_for_contributor(self):
        contributor = UserFactory()
        ProjectAuthFactory(
            project=self.project,
            user=contributor,
            role=ProjectAuthorizationRole.CONTRIBUTOR.value,
        )
        self.client.force_authenticate(user=contributor)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["writable"])

    def test_get_unknown_project_denied_by_permission(self):
        url = reverse(
            "project-guardrails-config",
            kwargs={"project_uuid": "00000000-0000-0000-0000-000000000000"},
        )
        response = self.client.get(url)
        # Permission layer denies before the view can return 404.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
