import threading
import time
from unittest import TestCase
from unittest.mock import MagicMock

from inline_agents.backends.openai.grpc.streaming_client import StreamingSession


def _stream_response(*, is_final: bool = False, status: str = "success"):
    response = MagicMock()
    response.status = status
    response.msg_id = "msg-1"
    response.message = "Acknowledged"
    response.sequence = 1
    response.is_final = is_final
    response.error_code = ""
    response.error_message = ""
    response.data = {}
    return response


class StreamingSessionResponseHandlingTestCase(TestCase):
    def test_stays_active_when_server_marks_delta_ack_as_final(self):
        """Delta acks with is_final must not close the session before send_completed."""
        stub = MagicMock()

        def open_stream_iterator():
            yield _stream_response(is_final=True)
            while True:
                time.sleep(0.05)

        session = StreamingSession(
            stub=stub,
            msg_id="msg-1",
            channel_uuid="channel-1",
            contact_urn="ext:user@example.com",
        )
        session._stream_active = True
        session._setup_complete = True

        worker = threading.Thread(target=session._process_responses, args=(open_stream_iterator(),))
        worker.start()
        time.sleep(0.1)

        try:
            self.assertTrue(session.is_active)
            self.assertTrue(session.send_completed("Final answer after handoff"))
        finally:
            session.close()
            worker.join(timeout=2)

    def test_breaks_read_loop_after_client_sent_completed(self):
        session = StreamingSession(
            stub=MagicMock(),
            msg_id="msg-1",
            channel_uuid="channel-1",
            contact_urn="ext:user@example.com",
        )
        session._stream_active = True
        session._setup_complete = True
        session._completed_sent = True
        session._response_thread = None

        session._process_responses(
            iter(
                [
                    _stream_response(is_final=False),
                    _stream_response(is_final=True),
                ]
            )
        )

        self.assertFalse(session.is_active)

    def test_send_completed_fails_when_stream_already_closed(self):
        session = StreamingSession(
            stub=MagicMock(),
            msg_id="msg-1",
            channel_uuid="channel-1",
            contact_urn="ext:user@example.com",
        )
        session._stream_active = False
        session._response_thread = None

        self.assertFalse(session.send_completed("Too late"))
