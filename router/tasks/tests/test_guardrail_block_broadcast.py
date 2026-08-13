from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from router.clients.flows.http.send_message import WhatsAppBroadcastHTTPClient
from router.clients.preview.simulator.broadcast import SimulateBroadcast
from router.tasks.actions_client import get_guardrail_block_broadcast_client
from router.tasks.invoke import UnsafeMessageException
from router.tasks.redis_task_manager import RedisTaskManager
from router.tasks.workflow_orchestrator import WorkflowContext, _handle_guardrails_block


class GetGuardrailBlockBroadcastClientTestCase(SimpleTestCase):
    def test_preview_uses_simulate_broadcast(self):
        client = get_guardrail_block_broadcast_client(preview=True)
        self.assertIsInstance(client, SimulateBroadcast)

    def test_non_preview_uses_classic_whatsapp_broadcast(self):
        client = get_guardrail_block_broadcast_client(preview=False)
        self.assertIsInstance(client, WhatsAppBroadcastHTTPClient)


class HandleGuardrailsBlockBroadcastTestCase(SimpleTestCase):
    @patch("router.tasks.workflow_orchestrator.dispatch")
    @patch("router.tasks.workflow_orchestrator.notify_async")
    @patch("router.tasks.workflow_orchestrator.get_guardrail_block_broadcast_client")
    def test_uses_guardrail_block_client_not_ctx_broadcast(self, mock_get_client, _mock_notify, mock_dispatch):
        classic = MagicMock(name="classic_broadcast")
        mock_get_client.return_value = classic
        mock_dispatch.return_value = "ok"

        task_manager = MagicMock(spec=RedisTaskManager)
        ctx = WorkflowContext(
            workflow_id="wf-1",
            project_uuid="proj-1",
            contact_urn="ext:user@example.com",
            message={
                "project_uuid": "proj-1",
                "contact_urn": "ext:user@example.com",
                "text": "fale sobre politica",
                "channel_uuid": "ch-1",
            },
            preview=False,
            preview_websocket=False,
            simulation_channel=True,
            language="pt-br",
            user_email="user@example.com",
            task_id="task-1",
            task_manager=task_manager,
            broadcast=MagicMock(name="grpc_stream_broadcast"),
            agents_backend="OpenAIBackend",
            flows_user_email="flows@example.com",
        )

        result = _handle_guardrails_block(ctx, UnsafeMessageException("blocked"))

        self.assertEqual(result, "ok")
        mock_get_client.assert_called_once_with(preview=False)
        mock_dispatch.assert_called_once()
        self.assertIs(mock_dispatch.call_args.kwargs["direct_message"], classic)
