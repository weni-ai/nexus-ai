from unittest.mock import MagicMock

from router.dispatcher import dispatch
from router.entities import Message


def test_dispatch_with_direct_message_calls_send():
    dm = MagicMock()
    msg = Message(project_uuid="p", text="t", contact_urn="u")
    out = dispatch(message=msg, user_email="user", llm_response="resp", direct_message=dm)
    assert out is not None
    dm.send_direct_message.assert_called_once()


def test_dispatch_flow_start_called_when_no_direct_message():
    fs = MagicMock()
    msg = Message(project_uuid="p", text="t", contact_urn="u")

    class DummyFlow:
        uuid = "f"
        name = "n"
        prompt = "p"
        pk = "pk"

    flow = DummyFlow()
    dispatch(message=msg, user_email="user", llm_response="resp", flow_start=fs, flow=flow)
    fs.start_flow.assert_called_once()
