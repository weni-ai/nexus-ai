from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from router.clients.flows.http.send_message import (
    InstagramCommentBroadcastHTTPClient,
    SendMessageHTTPClient,
    WhatsAppBroadcastHTTPClient,
)
from router.clients.preview.simulator.broadcast import SimulateBroadcast, SimulateWhatsAppBroadcastHTTPClient
from router.tasks.actions_client import get_guardrail_block_broadcast_client
from router.tasks.invocation_context import CachedProjectData
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

    def test_preview_with_components_uses_simulate_whatsapp_broadcast(self):
        client = get_guardrail_block_broadcast_client(preview=True, project_use_components=True)
        self.assertIsInstance(client, SimulateWhatsAppBroadcastHTTPClient)

    def test_components_project_uses_whatsapp_broadcast(self):
        client = get_guardrail_block_broadcast_client(preview=False, project_use_components=True)
        self.assertIsInstance(client, WhatsAppBroadcastHTTPClient)

    def test_non_components_project_uses_send_message_client(self):
        """The webchat preview and production both reach Flows through /mr/msg/send."""
        client = get_guardrail_block_broadcast_client(preview=False)
        self.assertIsInstance(client, SendMessageHTTPClient)

    def test_never_uses_the_streaming_endpoint(self):
        """The block happens before the backend opens a gRPC session, so streaming has no session."""
        client = get_guardrail_block_broadcast_client(preview=False)
        self.assertFalse(client._SendMessageHTTPClient__use_grpc)

    def test_instagram_comment_uses_single_text_broadcast(self):
        client = get_guardrail_block_broadcast_client(
            preview=False,
            force_instagram_comment_broadcast=True,
        )
        self.assertIs(type(client), InstagramCommentBroadcastHTTPClient)


class HandleGuardrailsBlockBroadcastTestCase(SimpleTestCase):
    @patch("router.tasks.workflow_orchestrator.dispatch")
    @patch("router.tasks.workflow_orchestrator.notify_async")
    @patch("router.tasks.workflow_orchestrator.get_guardrail_block_broadcast_client")
    def test_uses_guardrail_block_client_not_ctx_broadcast(self, mock_get_client, _mock_notify, mock_dispatch):
        dedicated = MagicMock(name="dedicated_broadcast")
        mock_get_client.return_value = dedicated
        mock_dispatch.return_value = "ok"

        task_manager = MagicMock(spec=RedisTaskManager)
        ctx = _build_context(task_manager, preview=False, preview_websocket=False)

        result = _handle_guardrails_block(ctx, UnsafeMessageException("blocked"))

        self.assertEqual(result, "ok")
        mock_get_client.assert_called_once_with(
            preview=False,
            project_use_components=False,
            force_instagram_comment_broadcast=False,
        )
        mock_dispatch.assert_called_once()
        self.assertIs(mock_dispatch.call_args.kwargs["direct_message"], dedicated)

    @patch("router.tasks.workflow_orchestrator.dispatch")
    @patch("router.tasks.workflow_orchestrator.notify_async")
    @patch("router.tasks.workflow_orchestrator.get_guardrail_block_broadcast_client")
    def test_instagram_comment_forces_comment_broadcast(self, mock_get_client, _mock_notify, mock_dispatch):
        mock_dispatch.return_value = "ok"

        task_manager = MagicMock(spec=RedisTaskManager)
        ctx = WorkflowContext(
            workflow_id="wf-1",
            project_uuid="proj-1",
            contact_urn="instagram:5467890213",
            message={
                "project_uuid": "proj-1",
                "contact_urn": "instagram:5467890213",
                "text": "fale sobre politica",
                "channel_uuid": "ch-1",
                "metadata": {"overwrite_message": {"ig_comment": {"id": "30065221"}}},
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

        _handle_guardrails_block(ctx, UnsafeMessageException("blocked"))

        mock_get_client.assert_called_once_with(
            preview=False,
            project_use_components=False,
            force_instagram_comment_broadcast=True,
        )

    @patch("router.tasks.workflow_orchestrator.dispatch_preview")
    @patch("router.tasks.workflow_orchestrator.notify_async")
    @patch("router.tasks.workflow_orchestrator.get_guardrail_block_broadcast_client")
    def test_webchat_preview_uses_dedicated_client(self, mock_get_client, _mock_notify, mock_dispatch_preview):
        """preview_websocket must not fall back to the turn's streaming client."""
        dedicated = MagicMock(name="dedicated_broadcast")
        mock_get_client.return_value = dedicated
        mock_dispatch_preview.return_value = "ok"

        task_manager = MagicMock(spec=RedisTaskManager)
        ctx = _build_context(task_manager, preview=False, preview_websocket=True)

        result = _handle_guardrails_block(ctx, UnsafeMessageException("blocked"))

        self.assertEqual(result, "ok")
        mock_get_client.assert_called_once_with(
            preview=False,
            project_use_components=False,
            force_instagram_comment_broadcast=False,
        )
        self.assertIs(mock_dispatch_preview.call_args.args[2], dedicated)
        self.assertIsNot(mock_dispatch_preview.call_args.args[2], ctx.broadcast)

    @patch("router.tasks.workflow_orchestrator.dispatch")
    @patch("router.tasks.workflow_orchestrator.notify_async")
    @patch("router.tasks.workflow_orchestrator.get_guardrail_block_broadcast_client")
    def test_forwards_project_use_components_from_cached_data(self, mock_get_client, _mock_notify, mock_dispatch):
        mock_dispatch.return_value = "ok"

        task_manager = MagicMock(spec=RedisTaskManager)
        ctx = _build_context(task_manager, preview=False, preview_websocket=False)
        ctx.cached_data = MagicMock(spec=CachedProjectData)
        ctx.cached_data.project_dict = {"use_components": True}

        _handle_guardrails_block(ctx, UnsafeMessageException("blocked"))

        mock_get_client.assert_called_once_with(
            preview=False,
            project_use_components=True,
            force_instagram_comment_broadcast=False,
        )
