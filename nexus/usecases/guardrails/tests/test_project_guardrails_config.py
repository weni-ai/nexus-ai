from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase, override_settings
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

    def test_lazy_init_new_project_blocks_all_categories(self):
        project = ProjectFactory()

        config = self.use_case.get_or_initialize(project)

        self.assertTrue(config.initialized_as_new_project)
        self.assertTrue(config.prompt_injection_filter_enabled)
        self.assertEqual(len(config.category_states), len(self.use_case.catalog_slugs()))
        self.assertTrue(all(config.category_states.values()))
        self.assertIsNotNone(config.bedrock_guardrail_pool_id)
        self.assertTrue(config.bedrock_guardrail_identifier)
        self.assertEqual(config.bedrock_guardrail_version, "1")
        self._mock_get_or_create_pool.assert_called_once()

    def test_lazy_init_keeps_backfilled_unblocked_config(self):
        project = ProjectFactory()
        ProjectGuardrailsConfig.objects.create(
            project=project,
            category_states=self.use_case.build_default_category_states(blocked=False),
            initialized_as_new_project=False,
            prompt_injection_filter_enabled=False,
        )

        config = self.use_case.get_or_initialize(project)

        self.assertFalse(config.initialized_as_new_project)
        self.assertFalse(config.prompt_injection_filter_enabled)
        self.assertEqual(len(config.category_states), len(self.use_case.catalog_slugs()))
        self.assertFalse(any(config.category_states.values()))
        self.assertIsNone(config.bedrock_guardrail_pool_id)
        self._mock_get_or_create_pool.assert_not_called()

    def test_lazy_init_backfills_pool_when_blocked_without_assignment(self):
        project = ProjectFactory()
        ProjectGuardrailsConfig.objects.create(
            project=project,
            category_states=self.use_case.build_default_category_states(blocked=True),
            initialized_as_new_project=True,
            bedrock_guardrail_identifier="",
            bedrock_guardrail_version="",
        )

        config = self.use_case.get_or_initialize(project)

        self.assertIsNotNone(config.bedrock_guardrail_pool_id)
        self.assertTrue(config.bedrock_guardrail_identifier)
        self._mock_get_or_create_pool.assert_called_once()

    def test_lazy_init_pool_failure_is_fail_open(self):
        project = ProjectFactory()
        self._mock_get_or_create_pool.side_effect = BedrockGuardrailPoolError("aws down")

        config = self.use_case.get_or_initialize(project)

        self.assertTrue(all(config.category_states.values()))
        self.assertIsNone(config.bedrock_guardrail_pool_id)
        self.assertFalse(config.bedrock_guardrail_identifier)

    def test_merge_adds_new_catalog_slug_on_get(self):
        project = ProjectFactory()
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

    @override_settings(GUARDRAILS_DEFAULT_BLOCKING_MESSAGES={})
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

    @patch("nexus.usecases.guardrails.project_guardrails_config.ConnectRESTClient")
    @override_settings(
        GUARDRAILS_DEFAULT_BLOCKING_MESSAGES={
            "en-us": "EN default",
            "pt-br": "PT default",
            "es": "ES default",
        }
    )
    def test_effective_blocking_message_uses_project_language(self, mock_connect_cls):
        mock_connect_cls.return_value.get_project_language.return_value = "pt-br"
        project = ProjectFactory()
        config = ProjectGuardrailsConfig.objects.create(
            project=project,
            category_states=self.use_case.build_default_category_states(blocked=True),
            blocking_message=None,
            initialized_as_new_project=True,
        )

        message, is_custom = self.use_case.effective_blocking_message(config)

        self.assertFalse(is_custom)
        self.assertEqual(message, "PT default")
        mock_connect_cls.return_value.get_project_language.assert_called_once_with(str(project.uuid))

    @patch("nexus.usecases.guardrails.project_guardrails_config.ConnectRESTClient")
    @override_settings(
        GUARDRAILS_DEFAULT_BLOCKING_MESSAGES={
            "en-us": "EN default",
            "pt-br": "PT default",
            "es": "ES default",
        }
    )
    def test_effective_blocking_message_falls_back_to_pt_br(self, mock_connect_cls):
        mock_connect_cls.return_value.get_project_language.return_value = "fr-fr"
        project = ProjectFactory()
        config = ProjectGuardrailsConfig.objects.create(
            project=project,
            category_states=self.use_case.build_default_category_states(blocked=True),
            blocking_message=None,
            initialized_as_new_project=True,
        )

        message, is_custom = self.use_case.effective_blocking_message(config)

        self.assertFalse(is_custom)
        self.assertEqual(message, "PT default")

    @patch("nexus.usecases.guardrails.project_guardrails_config.ConnectRESTClient")
    @override_settings(
        GUARDRAILS_DEFAULT_BLOCKING_MESSAGES={
            "en-us": "EN default",
            "pt-br": "PT default",
            "es": "ES default",
        }
    )
    def test_effective_blocking_message_logs_connect_failure(self, mock_connect_cls):
        mock_connect_cls.return_value.get_project_language.side_effect = RuntimeError("connect down")
        project = ProjectFactory()
        config = ProjectGuardrailsConfig.objects.create(
            project=project,
            category_states=self.use_case.build_default_category_states(blocked=True),
            blocking_message=None,
            initialized_as_new_project=True,
        )

        with self.assertLogs(
            "nexus.usecases.guardrails.project_guardrails_config",
            level="WARNING",
        ) as logs:
            message, is_custom = self.use_case.effective_blocking_message(config)

        self.assertFalse(is_custom)
        self.assertEqual(message, "PT default")
        self.assertTrue(any("Failed to fetch project language" in line for line in logs.output))

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
        self.use_case.get_or_initialize(project)

        config = self.use_case.update_config(
            project,
            category_states={"politics": False},
        )

        self.assertFalse(config.category_states["politics"])

    def test_update_message_only_leaves_category_states(self):
        project = ProjectFactory()
        ProjectGuardrailsConfig.objects.create(
            project=project,
            category_states=self.use_case.build_default_category_states(blocked=True),
            initialized_as_new_project=True,
            bedrock_guardrail_identifier="",
            bedrock_guardrail_version="",
        )
        self._mock_get_or_create_pool.reset_mock()

        updated = self.use_case.update_config(
            project,
            blocking_message="Brand refusal",
        )

        self.assertEqual(updated.blocking_message, "Brand refusal")
        self.assertTrue(all(updated.category_states.values()))
        self.assertFalse(updated.bedrock_guardrail_identifier)
        self._mock_get_or_create_pool.assert_not_called()

    def test_get_runtime_config_as_dict_includes_pool_and_message(self):
        project = ProjectFactory()
        self.use_case.get_or_initialize(project)
        ProjectGuardrailsConfig.objects.filter(project=project).update(
            category_states=self.use_case.build_default_category_states(blocked=False),
        )
        config = self.use_case.update_config(
            project,
            category_states={"politics": True},
            blocking_message="Custom runtime message",
        )

        runtime = self.use_case.get_runtime_config_as_dict(str(project.uuid))

        self.assertTrue(runtime["has_blocked_category"])
        self.assertEqual(runtime["guardrailIdentifier"], config.bedrock_guardrail_identifier)
        self.assertEqual(runtime["guardrailVersion"], "1")
        self.assertEqual(runtime["blocking_message"], "Custom runtime message")
        self.assertTrue(runtime["prompt_injection_filter_enabled"])

    def test_update_prompt_injection_filter_does_not_call_bedrock_pool(self):
        project = ProjectFactory()
        self.use_case.get_or_initialize(project)
        ProjectGuardrailsConfig.objects.filter(project=project).update(
            prompt_injection_filter_enabled=False,
        )
        self._mock_get_or_create_pool.reset_mock()

        updated = self.use_case.set_prompt_injection_filter_enabled(project, enabled=True)

        self.assertTrue(updated.prompt_injection_filter_enabled)
        self.assertTrue(self.use_case.get_prompt_injection_filter_enabled(project))
        self._mock_get_or_create_pool.assert_not_called()
        runtime = self.use_case.get_runtime_config_as_dict(str(project.uuid))
        self.assertTrue(runtime["prompt_injection_filter_enabled"])

    def test_get_runtime_config_as_dict_missing_project_skips_gate(self):
        runtime = self.use_case.get_runtime_config_as_dict("00000000-0000-0000-0000-000000000000")
        self.assertFalse(runtime["has_blocked_category"])
        self.assertIsNone(runtime["guardrailIdentifier"])
        self.assertFalse(runtime["prompt_injection_filter_enabled"])

    def test_get_runtime_config_as_dict_initializes_missing_config(self):
        project = ProjectFactory()
        self.assertFalse(ProjectGuardrailsConfig.objects.filter(project=project).exists())

        runtime = self.use_case.get_runtime_config_as_dict(str(project.uuid))

        self.assertTrue(ProjectGuardrailsConfig.objects.filter(project=project).exists())
        self.assertTrue(runtime["has_blocked_category"])
        self.assertIsNotNone(runtime["guardrailIdentifier"])
        self.assertEqual(runtime["guardrailVersion"], "1")

    def test_update_category_assigns_pool_identifier_and_version(self):
        project = ProjectFactory()
        self.use_case.get_or_initialize(project)
        ProjectGuardrailsConfig.objects.filter(project=project).update(
            category_states=self.use_case.build_default_category_states(blocked=False),
            bedrock_guardrail_pool=None,
            bedrock_guardrail_identifier=None,
            bedrock_guardrail_version=None,
        )
        self._mock_get_or_create_pool.reset_mock()

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
            bedrock_guardrail_pool=None,
            bedrock_guardrail_identifier=None,
            bedrock_guardrail_version=None,
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
                bedrock_guardrail_pool=None,
                bedrock_guardrail_identifier=None,
                bedrock_guardrail_version=None,
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
            bedrock_guardrail_pool=None,
            bedrock_guardrail_identifier=None,
            bedrock_guardrail_version=None,
        )
        self._mock_get_or_create_pool.side_effect = BedrockGuardrailPoolError("AccessDenied")

        with self.assertRaises(BedrockGuardrailPoolError):
            self.use_case.update_config(project, category_states={"politics": True})

        config = ProjectGuardrailsConfig.objects.get(project=project)
        self.assertFalse(config.category_states["politics"])
        self.assertIsNone(config.bedrock_guardrail_pool_id)

    @override_settings(
        AWS_BEDROCK_REGION_NAME="us-east-1",
        GUARDRAILS_DEFAULT_BLOCKING_MESSAGES={
            "en-us": "Default refusal",
            "pt-br": "Default refusal",
            "es": "Default refusal",
        },
    )
    def test_apply_input_guardrail_skips_when_no_blocked_categories(self):
        client = MagicMock()
        result = ProjectGuardrailsConfigUseCase.apply_input_guardrail(
            "Talk about politics",
            {
                "has_blocked_category": False,
                "guardrailIdentifier": "gr-1",
                "guardrailVersion": "1",
                "blocking_message": "Custom",
            },
            client=client,
        )
        self.assertIsNone(result)
        client.apply_guardrail.assert_not_called()

    @override_settings(
        AWS_BEDROCK_REGION_NAME="us-east-1",
        GUARDRAILS_DEFAULT_BLOCKING_MESSAGES={
            "en-us": "Default refusal",
            "pt-br": "Default refusal",
            "es": "Default refusal",
        },
    )
    def test_apply_input_guardrail_intervene_returns_project_message(self):
        client = MagicMock()
        client.apply_guardrail.return_value = {
            "action": "GUARDRAIL_INTERVENED",
            "outputs": [{"text": "Bedrock canned text"}],
        }
        result = ProjectGuardrailsConfigUseCase.apply_input_guardrail(
            "Who should I vote for?",
            {
                "has_blocked_category": True,
                "guardrailIdentifier": "gr-1",
                "guardrailVersion": "1",
                "blocking_message": "Project refusal message",
            },
            client=client,
        )
        self.assertEqual(result, "Project refusal message")
        self.assertEqual(client.apply_guardrail.call_args.kwargs["source"], "INPUT")

    @override_settings(
        AWS_BEDROCK_REGION_NAME="us-east-1",
        GUARDRAILS_DEFAULT_BLOCKING_MESSAGES={
            "en-us": "Default refusal",
            "pt-br": "Default refusal",
            "es": "Default refusal",
        },
    )
    def test_apply_input_guardrail_fail_open_on_bedrock_error(self):
        from botocore.exceptions import ClientError

        client = MagicMock()
        client.apply_guardrail.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
            "ApplyGuardrail",
        )
        with patch("nexus.usecases.guardrails.project_guardrails_config.sentry_sdk.capture_exception"):
            result = ProjectGuardrailsConfigUseCase.apply_input_guardrail(
                "Hello",
                {
                    "has_blocked_category": True,
                    "guardrailIdentifier": "gr-1",
                    "guardrailVersion": "1",
                    "blocking_message": "Custom",
                },
                client=client,
            )
        self.assertIsNone(result)


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
