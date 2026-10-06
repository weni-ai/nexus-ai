from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from router.tasks.invoke import (
    apply_simulation_foundation_model_override,
    apply_simulation_supervisor_agent_override,
    resolve_simulation_pipeline_replacement,
)
from router.tasks.workflow_orchestrator import WorkflowContext, _run_generation

MANAGER_UUID = "11111111-1111-1111-1111-111111111111"


def _redis_get(value):
    client = MagicMock()
    if value is None:
        client.get.return_value = None
    else:
        client.get.return_value = value.encode("utf-8")
    return client


class SimulationManagerOverrideTest(SimpleTestCase):
    def test_foundation_override_skips_outside_simulation(self):
        result = apply_simulation_foundation_model_override(False, "proj", "ext:user@weni.ai", "gpt-4.1")
        self.assertEqual(result, "gpt-4.1")

    @patch("router.tasks.invoke._simulation_manager_switch_blocked", return_value=False)
    @patch("router.tasks.invoke.get_redis_read_client")
    def test_foundation_override_ignores_manager_uuid(self, mock_redis, _blocked):
        mock_redis.return_value = _redis_get(MANAGER_UUID)
        result = apply_simulation_foundation_model_override(True, "proj", "ext:user@weni.ai", "gpt-4.1")
        self.assertEqual(result, "gpt-4.1")

    @patch("router.tasks.invoke._simulation_manager_switch_blocked", return_value=False)
    @patch("router.tasks.invoke.get_redis_read_client")
    def test_foundation_override_applies_model_name(self, mock_redis, _blocked):
        mock_redis.return_value = _redis_get("gpt-4.1-mini")
        result = apply_simulation_foundation_model_override(True, "proj", "ext:user@weni.ai", "gpt-4.1")
        self.assertEqual(result, "gpt-4.1-mini")

    @patch("router.tasks.invoke._simulation_manager_switch_blocked", return_value=False)
    @patch("router.tasks.invoke.get_redis_read_client")
    def test_supervisor_override_uses_cached_manager_uuid(self, mock_redis, _blocked):
        mock_redis.return_value = _redis_get(MANAGER_UUID)
        result = apply_simulation_supervisor_agent_override(True, "proj", "ext:user@weni.ai", None)
        self.assertEqual(result, MANAGER_UUID)

    def test_supervisor_override_keeps_explicit_task_uuid(self):
        result = apply_simulation_supervisor_agent_override(True, "proj", "ext:user@weni.ai", "explicit-manager")
        self.assertEqual(result, "explicit-manager")

    @patch("router.tasks.invoke._simulation_manager_switch_blocked", return_value=True)
    @patch("router.tasks.invoke.get_redis_read_client")
    def test_supervisor_override_skips_hidden_project_manager(self, mock_redis, _blocked):
        mock_redis.return_value = _redis_get(MANAGER_UUID)
        result = apply_simulation_supervisor_agent_override(True, "proj", "ext:user@weni.ai", None)
        self.assertIsNone(result)

    @patch("router.tasks.invoke._simulation_manager_switch_blocked", return_value=False)
    @patch("router.tasks.invoke.get_redis_read_client")
    def test_supervisor_override_ignores_model_name(self, mock_redis, _blocked):
        mock_redis.return_value = _redis_get("gpt-4.1")
        result = apply_simulation_supervisor_agent_override(True, "proj", "ext:user@weni.ai", None)
        self.assertIsNone(result)

    @patch("router.tasks.invoke.get_redis_read_client")
    def test_pipeline_replacement_forces_new_pipeline(self, mock_redis):
        mock_redis.return_value = _redis_get("new")
        replace, version = resolve_simulation_pipeline_replacement(True, "proj", "ext:user@weni.ai", "2.6")
        self.assertTrue(replace)
        self.assertIsNone(version)

    @patch("router.tasks.invoke.get_redis_read_client")
    def test_pipeline_replacement_uses_legacy_token(self, mock_redis):
        mock_redis.return_value = _redis_get("2.6")
        replace, version = resolve_simulation_pipeline_replacement(True, "proj", "ext:user@weni.ai", None)
        self.assertTrue(replace)
        self.assertEqual(version, "2.6")

    @patch("router.tasks.invoke.get_redis_read_client")
    def test_pipeline_replacement_keeps_project_pipeline_without_cache(self, mock_redis):
        mock_redis.return_value = _redis_get(None)
        replace, version = resolve_simulation_pipeline_replacement(True, "proj", "ext:user@weni.ai", "2.6")
        self.assertFalse(replace)
        self.assertEqual(version, "2.6")


class WorkflowPreviewManagerTest(SimpleTestCase):
    def _context(self):
        return WorkflowContext(
            workflow_id="wf-preview",
            project_uuid="project-uuid",
            contact_urn="ext:user@weni.ai",
            message={"project_uuid": "project-uuid", "contact_urn": "ext:user@weni.ai", "text": "ola"},
            preview=False,
            preview_websocket=True,
            simulation_channel=True,
            language="pt-br",
            user_email="user@weni.ai",
            task_id="task-123",
            task_manager=MagicMock(),
        )

    @patch("router.tasks.workflow_orchestrator._invoke_backend")
    @patch("router.tasks.workflow_orchestrator.BackendsRegistry.get_backend")
    @patch("router.tasks.workflow_orchestrator.should_skip_conversation_sqs", return_value=True)
    @patch("router.tasks.workflow_orchestrator._extract_and_apply_message_context")
    @patch("router.tasks.workflow_orchestrator._create_message_object")
    @patch("router.tasks.workflow_orchestrator.apply_simulation_foundation_model_override", return_value="gpt-4.1")
    @patch(
        "router.tasks.workflow_orchestrator.apply_simulation_supervisor_agent_override",
        return_value=MANAGER_UUID,
    )
    @patch(
        "router.tasks.workflow_orchestrator.resolve_simulation_pipeline_replacement",
        return_value=(True, None),
    )
    @patch("router.tasks.workflow_orchestrator._preprocess_message_input")
    def test_generation_uses_preview_manager_and_pipeline(
        self,
        mock_preprocess,
        _mock_pipeline,
        _mock_supervisor,
        _mock_model,
        mock_create_message,
        _mock_extract_context,
        _mock_skip_sqs,
        _mock_get_backend,
        mock_invoke_backend,
    ):
        ctx = self._context()
        ctx.cached_data = MagicMock(guardrails_config={}, project_dict={"manager_pipeline_version": "2.6"})
        ctx.agents_backend = "OpenAIBackend"
        mock_preprocess.return_value = (ctx.message, "gpt-4.1", False)
        mock_create_message.return_value = MagicMock(text="ola", channel_uuid="channel", contact_name="")
        mock_invoke_backend.return_value = ("oi", False)

        self.assertEqual(_run_generation(ctx), ("oi", False))
        self.assertEqual(mock_invoke_backend.call_args.kwargs["supervisor_agent_uuid"], MANAGER_UUID)
        self.assertTrue(mock_invoke_backend.call_args.kwargs["replace_manager_pipeline_version"])
        self.assertIsNone(mock_invoke_backend.call_args.kwargs["manager_pipeline_version"])
        self.assertEqual(mock_invoke_backend.call_args.kwargs["foundation_model"], "gpt-4.1")
