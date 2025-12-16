import os
from unittest.mock import patch

from router.tasks.tasks import task_send_message_http_client


@patch.dict(os.environ, {"FLOWS_REST_ENDPOINT": "http://e", "FLOWS_SEND_MESSAGE_INTERNAL_TOKEN": "it"})
def test_task_send_message_http_client(monkeypatch):
    sent = {}

    class DummyClient:
        def __init__(self, *a):
            pass

        def send_direct_message(self, **kwargs):
            sent.update(kwargs)

    monkeypatch.setattr("router.tasks.tasks.SendMessageHTTPClient", DummyClient)
    task_send_message_http_client.delay = lambda **kwargs: task_send_message_http_client(**kwargs)

    task_send_message_http_client(text="x", urns=["u"], project_uuid="p", user="f", full_chunks=[{"c": 1}])
    assert sent["text"] == "x" and sent["project_uuid"] == "p" and sent["urns"] == ["u"]
