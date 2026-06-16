from unittest import TestCase
from unittest.mock import MagicMock, patch

from inline_agents.backends.openai.backend import OpenAIBackend


class InitializeGrpcSessionTestCase(TestCase):
    @patch("inline_agents.backends.openai.backend.is_grpc_enabled", return_value=True)
    @patch("inline_agents.backends.openai.backend.MessageStreamingClient")
    def test_prefers_msg_external_id(self, mock_client_cls, _mock_enabled):
        backend = OpenAIBackend()
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_session.start.return_value = True
        mock_client.create_streaming_session.return_value = mock_session
        mock_client_cls.return_value = mock_client

        _, _, msg_id = backend._initialize_grpc_session(
            channel_uuid="channel-1",
            contact_urn="ext:user@example.com",
            session_id="session-1",
            project_uuid="project-1",
            language="en",
            use_components=False,
            stream_support=True,
            msg_external_id="flows-msg-id-99",
        )

        self.assertEqual(msg_id, "flows-msg-id-99")
        self.assertEqual(mock_client.create_streaming_session.call_args.kwargs["msg_id"], "flows-msg-id-99")
