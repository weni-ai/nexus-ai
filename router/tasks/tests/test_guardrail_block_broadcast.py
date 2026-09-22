from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from router.clients.flows.http.send_message import WhatsAppBroadcastHTTPClient
from router.clients.preview.simulator.broadcast import SimulateBroadcast
from router.tasks.actions_client import (
    get_guardrail_block_broadcast_client,
    resolve_guardrail_block_broadcast_client,
)
from router.tasks.invoke import UnsafeMessageException
from router.tasks.redis_task_manager import RedisTaskManager
from router.tasks.workflow_orchestrator import WorkflowContext, _handle_guardrails_block


def _build_context(task_manager, *, preview: bool, preview_websocket: bool) -> WorkflowContext:
    return WorkflowContext(
        workflow_id="wf-1",
        project_uuid="proj-1",
        contact_urn="ext:user@example.com",
        message={
            "project_uuid": "proj-1",
            "contact_urn": "ext:user@example.com",
            "text": "fale sobre politica",
            "channel_uuid": "ch-1",
        },
        preview=preview,
        preview_websocket=preview_websocket,
        simulation_channel=True,
        language="pt-br",
        user_email="user@example.com",
        task_id="task-1",
        task_manager=task_manager,
        broadcast=MagicMock(name="grpc_stream_broadcast"),
        agents_backend="OpenAIBackend",
        flows_user_email="flows@example.com",
    )


class GetGuardrailBlockBroadcastClientTestCase(SimpleTestCase):
    def test_preview_uses_simulate_broadcast(self):
        client = get_guardrail_block_broadcast_client(preview=True)
        self.assertIsInstance(client, SimulateBroadcast)

    def test_non_preview_uses_classic_whatsapp_broadcast(self):
        client = get_guardrail_block_broadcast_client(preview=False)
        self.assertIsInstance(client, WhatsAppBroadcastHTTPClient)


class ResolveGuardrailBlockBroadcastClientTestCase(SimpleTestCase):
    def test_webchat_preview_reuses_turn_broadcast(self):
        turn_broadcast = MagicMock(name="stream_broadcast")

        client = resolve_guardrail_block_broadcast_client(
            preview=False,
            preview_websocket=True,
            turn_broadcast=turn_broadcast,
        )

        self.assertIs(client, turn_broadcast)

    def test_classic_preview_ignores_turn_broadcast(self):
        client = resolve_guardrail_block_broadcast_client(
            preview=True,
            preview_websocket=True,
            turn_broadcast=MagicMock(name="stream_broadcast"),
        )

        self.assertIsInstance(client, SimulateBroadcast)

    def test_production_uses_classic_whatsapp_broadcast(self):
        client = resolve_guardrail_block_broadcast_client(
            preview=False,
            preview_websocket=False,
            turn_broadcast=MagicMock(name="stream_broadcast"),
        )

        self.assertIsInstance(client, WhatsAppBroadcastHTTPClient)

    def test_webchat_preview_without_turn_broadcast_falls_back(self):
        client = resolve_guardrail_block_broadcast_client(
            preview=False,
            preview_websocket=True,
            turn_broadcast=None,
        )

        self.assertIsInstance(client, WhatsAppBroadcastHTTPClient)


class HandleGuardrailsBlockBroadcastTestCase(SimpleTestCase):
    @patch("router.tasks.workflow_orchestrator.dispatch")
    @patch("router.tasks.workflow_orchestrator.notify_async")
    @patch("router.tasks.workflow_orchestrator.resolve_guardrail_block_broadcast_client")
    def test_uses_guardrail_block_client_not_ctx_broadcast(self, mock_resolve_client, _mock_notify, mock_dispatch):
        classic = MagicMock(name="classic_broadcast")
        mock_resolve_client.return_value = classic
        mock_dispatch.return_value = "ok"

        task_manager = MagicMock(spec=RedisTaskManager)
        ctx = _build_context(task_manager, preview=False, preview_websocket=False)

        result = _handle_guardrails_block(ctx, UnsafeMessageException("blocked"))

        self.assertEqual(result, "ok")
        mock_resolve_client.assert_called_once_with(
            preview=False,
            preview_websocket=False,
            turn_broadcast=ctx.broadcast,
        )
        mock_dispatch.assert_called_once()
        self.assertIs(mock_dispatch.call_args.kwargs["direct_message"], classic)

    @patch("router.tasks.workflow_orchestrator.dispatch_preview")
    @patch("router.tasks.workflow_orchestrator.notify_async")
    def test_webchat_preview_reaches_widget_through_turn_broadcast(self, _mock_notify, mock_dispatch_preview):
        """The webchat preview renders from Flows, so the block reply must reuse the turn's client."""
        mock_dispatch_preview.return_value = "ok"

        task_manager = MagicMock(spec=RedisTaskManager)
        ctx = _build_context(task_manager, preview=False, preview_websocket=True)

        result = _handle_guardrails_block(ctx, UnsafeMessageException("blocked"))

        self.assertEqual(result, "ok")
        mock_dispatch_preview.assert_called_once()
        self.assertIs(mock_dispatch_preview.call_args.args[2], ctx.broadcast)
