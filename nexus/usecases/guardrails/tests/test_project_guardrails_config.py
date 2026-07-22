from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone as django_timezone
from rest_framework.request import Request

from nexus.projects.api.permissions import GuardrailsConfigAdminPermission
from nexus.projects.models import ProjectAuthorizationRole, ProjectGuardrailsConfig
from nexus.usecases.guardrails.bedrock_guardrail_pool import BedrockGuardrailPoolError
from nexus.usecases.guardrails.project_guardrails_config import ProjectGuardrailsConfigUseCase
from nexus.usecases.guardrails.tests.guardrail_test_helpers import fake_pool_resolve as _fake_pool_resolve
from nexus.usecases.projects.tests.project_factory import ProjectAuthFactory, ProjectFactory
from nexus.usecases.users.tests.user_factory import UserFactory


class ProjectGuardrailsConfigUseCaseTestCase(TestCase):
    def setUp(self) -> None:
        self.use_case = ProjectGuardrailsConfigUseCase()
        self._pool_patcher = patch(
            "nexus.usecases.guardrails.project_guardrails_config.BedrockGuardrailPoolService.get_or_create_pool",
            side_effect=_fake_pool_resolve,
        )
        self._mock_get_or_create_pool = self._pool_patcher.start()

    def tearDown(self) -> None:
        self._pool_patcher.stop()

    @override_settings(GUARDRAILS_CONFIG_FEATURE_DEPLOY_AT=datetime(2026, 7, 1, tzinfo=timezone.utc))
    def test_lazy_init_new_project_blocks_all_categories(self):
        project = ProjectFactory()
        project.created_at = django_timezone.make_aware(datetime(2026, 8, 1))
        project.save(update_fields=["created_at"])

        config = self.use_case.get_or_initialize(project)

        self.assertTrue(config.initialized_as_new_project)
        self.assertEqual(len(config.category_states), len(self.use_case.catalog_slugs()))
        self.assertTrue(all(config.category_states.values()))

    @override_settings(GUARDRAILS_CONFIG_FEATURE_DEPLOY_AT=datetime(2026, 7, 1, tzinfo=timezone.utc))
    def test_lazy_init_existing_project_unblocks_all_categories(self):
        project = ProjectFactory()
        project.created_at = django_timezone.make_aware(datetime(2025, 1, 1))
        project.save(update_fields=["created_at"])

        config = self.use_case.get_or_initialize(project)

        self.assertFalse(config.initialized_as_new_project)
        self.assertEqual(len(config.category_states), len(self.use_case.catalog_slugs()))
        self.assertFalse(any(config.category_states.values()))

    @override_settings(GUARDRAILS_CONFIG_FEATURE_DEPLOY_AT=datetime(2026, 7, 1, tzinfo=timezone.utc))
    def test_merge_adds_new_catalog_slug_on_get(self):
        project = ProjectFactory()
        project.created_at = django_timezone.make_aware(datetime(2025, 1, 1))
        project.save(update_fields=["created_at"])

        ProjectGuardrailsConfig.objects.create(
            project=project,
            category_states={"politics": True},
            initialized_as_new_project=False,
        )

        with patch.object(
            ProjectGuardrailsConfigUseCase,
            "catalog_slugs",
            return_value=["politics", "bias"],
        ):
            refreshed = self.use_case.get_or_initialize(project)

        self.assertTrue(refreshed.category_states["politics"])
        self.assertFalse(refreshed.category_states["bias"])

    def test_sanitize_category_states_strips_unknown_slugs(self):
        sanitized = self.use_case.sanitize_category_states(
            {"politics": True, "unknown_slug": False, "bias": "invalid"},
        )

        self.assertEqual(sanitized, {"politics": True})

    def test_validate_category_states_rejects_unknown_slug(self):
        with self.assertRaises(ValidationError):
            self.use_case.validate_category_states({"unknown_slug": True})

    @override_settings(GUARDRAILS_DEFAULT_BLOCKING_MESSAGE="")
    def test_validate_blocking_message_requires_message_when_blocked(self):
        states = self.use_case.build_default_category_states(blocked=True)

        with self.assertRaises(ValidationError):
            self.use_case.validate_blocking_message_for_states("   ", states)

    def test_effective_blocking_message_uses_settings_default(self):
        project = ProjectFactory()
        config = ProjectGuardrailsConfig.objects.create(
            project=project,
            category_states=self.use_case.build_default_category_states(blocked=True),
            blocking_message=None,
            initialized_as_new_project=True,
        )

        message, is_custom = self.use_case.effective_blocking_message(config)

        self.assertFalse(is_custom)
        self.assertTrue(message)

    def test_effective_blocking_message_uses_custom_value(self):
        project = ProjectFactory()
        config = ProjectGuardrailsConfig.objects.create(
            project=project,
            category_states=self.use_case.build_default_category_states(blocked=True),
            blocking_message="Custom refusal",
            initialized_as_new_project=True,
        )

        message, is_custom = self.use_case.effective_blocking_message(config)

        self.assertTrue(is_custom)
        self.assertEqual(message, "Custom refusal")

    def test_update_unblocks_without_confirmation(self):
        project = ProjectFactory()
        project.created_at = django_timezone.make_aware(datetime(2026, 8, 1))
        project.save(update_fields=["created_at"])
        self.use_case.get_or_initialize(project)

        config = self.use_case.update_config(
            project,
            category_states={"politics": False},
        )

        self.assertFalse(config.category_states["politics"])

    def test_update_message_only_leaves_category_states(self):
        project = ProjectFactory()
        config = self.use_case.get_or_initialize(project)

        updated = self.use_case.update_config(
            project,
            blocking_message="Brand refusal",
            blocking_message_provided=True,
        )

        self.assertEqual(updated.blocking_message, "Brand refusal")
        self.assertEqual(updated.category_states, config.category_states)
        self._mock_get_or_create_pool.assert_not_called()

    def test_update_category_assigns_pool_identifier_and_version(self):
        project = ProjectFactory()
        self.use_case.get_or_initialize(project)
        ProjectGuardrailsConfig.objects.filter(project=project).update(
            category_states=self.use_case.build_default_category_states(blocked=False),
        )

        config = self.use_case.update_config(project, category_states={"politics": True})

        self.assertTrue(config.category_states["politics"])
        self.assertIsNotNone(config.bedrock_guardrail_pool_id)
        self.assertEqual(
            config.bedrock_guardrail_identifier, config.bedrock_guardrail_pool.bedrock_guardrail_identifier
        )
        self.assertEqual(config.bedrock_guardrail_version, "1")
        self._mock_get_or_create_pool.assert_called_once()

    def test_update_all_unblocked_clears_pool_assignment(self):
        project = ProjectFactory()
        self.use_case.get_or_initialize(project)
        ProjectGuardrailsConfig.objects.filter(project=project).update(
            category_states=self.use_case.build_default_category_states(blocked=False),
        )
        assigned = self.use_case.update_config(project, category_states={"politics": True})
        self.assertIsNotNone(assigned.bedrock_guardrail_pool_id)

        cleared = self.use_case.update_config(
            project,
            category_states=self.use_case.build_default_category_states(blocked=False),
        )

        self.assertIsNone(cleared.bedrock_guardrail_pool_id)
        self.assertIsNone(cleared.bedrock_guardrail_identifier)
        self.assertIsNone(cleared.bedrock_guardrail_version)

    def test_two_projects_with_same_subset_share_pool(self):
        project_a = ProjectFactory()
        project_b = ProjectFactory()
        for project in (project_a, project_b):
            self.use_case.get_or_initialize(project)
            ProjectGuardrailsConfig.objects.filter(project=project).update(
                category_states=self.use_case.build_default_category_states(blocked=False),
            )

        config_a = self.use_case.update_config(project_a, category_states={"politics": True, "bias": True})
        config_b = self.use_case.update_config(project_b, category_states={"bias": True, "politics": True})

        self.assertEqual(config_a.bedrock_guardrail_pool_id, config_b.bedrock_guardrail_pool_id)
        self.assertEqual(config_a.bedrock_guardrail_identifier, config_b.bedrock_guardrail_identifier)

    def test_update_category_propagates_bedrock_failure_without_saving(self):
        project = ProjectFactory()
        self.use_case.get_or_initialize(project)
        ProjectGuardrailsConfig.objects.filter(project=project).update(
            category_states=self.use_case.build_default_category_states(blocked=False),
        )
        self._mock_get_or_create_pool.side_effect = BedrockGuardrailPoolError("AccessDenied")

        with self.assertRaises(BedrockGuardrailPoolError):
            self.use_case.update_config(project, category_states={"politics": True})

        config = ProjectGuardrailsConfig.objects.get(project=project)
        self.assertFalse(config.category_states["politics"])
        self.assertIsNone(config.bedrock_guardrail_pool_id)


class GuardrailsConfigAdminPermissionTestCase(TestCase):
    def setUp(self) -> None:
        self.permission = GuardrailsConfigAdminPermission()
        self.factory = RequestFactory()
        self.view = MagicMock()
        self.project = ProjectFactory()

    def _build_request(self, method: str, user=None):
        django_request = self.factory.generic(method, "/")
        request = Request(django_request)
        if user is not None:
            request.user = user
            request._request.user = user
        self.view.kwargs = {"project_uuid": str(self.project.uuid)}
        return request

    def test_get_allowed_for_project_member(self):
        request = self._build_request("GET", user=self.project.created_by)

        allowed = self.permission.has_permission(request, self.view)

        self.assertTrue(allowed)

    def test_patch_allowed_for_moderator(self):
        request = self._build_request("PATCH", user=self.project.created_by)

        allowed = self.permission.has_permission(request, self.view)

        self.assertTrue(allowed)

    def test_patch_denied_for_contributor(self):
        contributor = UserFactory()
        ProjectAuthFactory(
            project=self.project,
            user=contributor,
            role=ProjectAuthorizationRole.CONTRIBUTOR.value,
        )
        request = self._build_request("PATCH", user=contributor)

        allowed = self.permission.has_permission(request, self.view)

        self.assertFalse(allowed)
