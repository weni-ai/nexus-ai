"""SkipDirectBroadcastResult: produção não faz dispatch; preview ainda despacha.

Executar com o runner do Django, por exemplo::

    python manage.py test router.tasks.tests.test_skip_direct_broadcast
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from inline_agents.backends.openai.invoke_result import SkipDirectBroadcastResult
from router.tasks.redis_task_manager import RedisTaskManager
from router.tasks.workflow_orchestrator import WorkflowContext, _run_post_generation


class SkipDirectBroadcastPostGenerationTestCase(TestCase):
    """Cobre _run_post_generation com SkipDirectBroadcastResult (workflow)."""

    def _minimal_ctx(self, *, preview: bool) -> WorkflowContext:
        tm = MagicMock(spec=RedisTaskManager)
        return WorkflowContext(
            workflow_id="wf-1",
            project_uuid="p1",
            contact_urn="tel:+1",
            message={
                "project_uuid": "p1",
                "contact_urn": "tel:+1",
                "text": "hi",
                "channel_uuid": "ch1",
            },
            preview=preview,
            language="en",
            user_email="u@x.com",
            task_id="t1",
            task_manager=tm,
            broadcast=MagicMock(),
            flows_user_email="flow@x.com",
            agents_backend="OpenAIBackend",
            incoming_created_at="2020-01-01T00:00:00Z",
            message_conversation_log_uuid="log-1",
            turn_id="turn-1",
        )

    def test_production_skips_dispatch(self):
        """Sem preview: não chama dispatch nem dispatch_preview."""
        ctx = self._minimal_ctx(preview=False)
        payload = [{"msg": {"text": "from tool"}}]
        with patch("router.tasks.workflow_orchestrator.dispatch") as mock_dispatch, patch(
            "router.tasks.workflow_orchestrator.dispatch_preview"
        ) as mock_dispatch_preview, patch("router.tasks.workflow_orchestrator.notify_async"):
            out = _run_post_generation(ctx, SkipDirectBroadcastResult(messages=payload))
        mock_dispatch.assert_not_called()
        mock_dispatch_preview.assert_not_called()
        self.assertIs(out, True)

    def test_preview_calls_dispatch_preview_with_messages(self):
        """Com preview: dispatch_preview recebe a lista messages."""
        ctx = self._minimal_ctx(preview=True)
        payload = [{"msg": {"text": "simulator"}}]
        with patch("router.tasks.workflow_orchestrator.dispatch") as mock_dispatch, patch(
            "router.tasks.workflow_orchestrator.dispatch_preview"
        ) as mock_dispatch_preview, patch("router.tasks.workflow_orchestrator.notify_async"):
            mock_dispatch_preview.return_value = "preview-msg"
            _run_post_generation(ctx, SkipDirectBroadcastResult(messages=payload))
        mock_dispatch.assert_not_called()
        mock_dispatch_preview.assert_called_once()
        args, _kwargs = mock_dispatch_preview.call_args
        self.assertEqual(args[0], payload)
