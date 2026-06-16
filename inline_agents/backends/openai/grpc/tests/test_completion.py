from unittest import TestCase
from unittest.mock import MagicMock

from inline_agents.backends.openai.grpc.completion import (
    _summarize_responses,
    _summarize_unary_result,
    deliver_final_grpc_stream,
)


class DeliverFinalGrpcStreamTestCase(TestCase):
    def test_delivers_via_session_when_active(self):
        grpc_session = MagicMock()
        grpc_session.is_active = True
        grpc_session.send_completed.return_value = True
        grpc_session.responses = [{"status": "success", "is_final": True, "data": {"received_type": "completed"}}]

        delivered = deliver_final_grpc_stream(
            "Final text",
            grpc_client=MagicMock(),
            grpc_session=grpc_session,
            grpc_msg_id="msg-123",
            channel_uuid="channel-1",
            contact_urn="ext:user@example.com",
            project_uuid="project-1",
        )

        self.assertTrue(delivered)
        grpc_session.send_completed.assert_called_once_with("Final text")

    def test_falls_back_when_session_ack_missing(self):
        grpc_session = MagicMock()
        grpc_session.is_active = True
        grpc_session.send_completed.return_value = True
        grpc_session.responses = []
        grpc_client = MagicMock()
        grpc_client.send_completed_message.return_value = {"status": "success"}

        delivered = deliver_final_grpc_stream(
            "Final text",
            grpc_client=grpc_client,
            grpc_session=grpc_session,
            grpc_msg_id="msg-123",
            channel_uuid="channel-1",
            contact_urn="ext:user@example.com",
            project_uuid="project-1",
        )

        self.assertTrue(delivered)
        grpc_client.send_completed_message.assert_called_once()

    def test_falls_back_when_session_inactive(self):
        grpc_session = MagicMock()
        grpc_session.is_active = False
        grpc_client = MagicMock()
        grpc_client.send_completed_message.return_value = {"status": "success"}

        delivered = deliver_final_grpc_stream(
            "Final text",
            grpc_client=grpc_client,
            grpc_session=grpc_session,
            grpc_msg_id="msg-123",
            channel_uuid="channel-1",
            contact_urn="ext:user@example.com",
            project_uuid="project-1",
        )

        self.assertTrue(delivered)
        grpc_client.send_completed_message.assert_called_once_with(
            msg_id="msg-123",
            content="Final text",
            channel_uuid="channel-1",
            contact_urn="ext:user@example.com",
            project_uuid="project-1",
        )

    def test_returns_false_when_unary_fails(self):
        grpc_client = MagicMock()
        grpc_client.send_completed_message.return_value = {"status": "error"}

        delivered = deliver_final_grpc_stream(
            "Final text",
            grpc_client=grpc_client,
            grpc_session=MagicMock(is_active=False),
            grpc_msg_id="msg-123",
            channel_uuid="channel-1",
            contact_urn="ext:user@example.com",
            project_uuid="project-1",
        )

        self.assertFalse(delivered)

    def test_skips_empty_text(self):
        grpc_session = MagicMock()
        grpc_session.is_active = True

        delivered = deliver_final_grpc_stream(
            "   ",
            grpc_client=MagicMock(),
            grpc_session=grpc_session,
            grpc_msg_id="msg-123",
            channel_uuid="channel-1",
            contact_urn="ext:user@example.com",
            project_uuid="project-1",
        )

        self.assertFalse(delivered)
        grpc_session.send_completed.assert_not_called()


class GrpcDeliveryLoggingTestCase(TestCase):
    def test_summarize_responses_empty(self):
        self.assertEqual(_summarize_responses([]), "(empty)")

    def test_summarize_responses_includes_ack_fields(self):
        summary = _summarize_responses(
            [
                {"status": "success", "is_final": False, "sequence": 1, "data": {"received_type": "setup"}},
                {"status": "success", "is_final": True, "sequence": 2, "data": {"received_type": "completed"}},
            ]
        )
        self.assertIn("received_type='completed'", summary)
        self.assertIn("2 total", summary)

    def test_summarize_unary_result(self):
        summary = _summarize_unary_result(
            {"status": "success", "is_final": True, "sequence": 1, "data": {"received_type": "completed"}}
        )
        self.assertIn("status='success'", summary)
        self.assertIn("received_type='completed'", summary)
