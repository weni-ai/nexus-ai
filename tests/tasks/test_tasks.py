from unittest.mock import MagicMock

from router.tasks.tasks import _initialize_and_handle_pending_response, _process_trace_event


def test_initialize_and_handle_pending_response(monkeypatch):
    class DummyRedis:
        def __init__(self):
            self.store = {}

        def get(self, k):
            v = self.store.get(k)
            return v.encode("utf-8") if isinstance(v, str) else v

        def set(self, k, v):
            self.store[k] = v

        def delete(self, k):
            self.store.pop(k, None)

    dummy_redis = DummyRedis()
    dummy_redis.store["multi_response:u"] = "prev"
    dummy_redis.store["multi_task:u"] = "old"

    monkeypatch.setattr("router.tasks.tasks.Redis", type("R", (), {"from_url": staticmethod(lambda url: dummy_redis)}))
    monkeypatch.setattr(
        "router.tasks.tasks.celery_app", type("C", (), {"control": type("X", (), {"revoke": lambda *a, **k: None})})()
    )

    message = {
        "project_uuid": "p",
        "text": "new",
        "contact_urn": "u",
        "metadata": {},
        "attachments": [],
        "msg_event": {},
    }
    rc, msg = _initialize_and_handle_pending_response(message, "newtask")

    assert msg.text == "prev\nnew"
    assert "multi_response:u" not in dummy_redis.store
    assert dummy_redis.store["multi_task:u"] == "newtask"


def test_process_trace_event_preview_sends_trace_update(monkeypatch):
    sent = []

    def fake_send_preview_message_to_websocket(*, project_uuid, user_email, message_data):
        sent.append(message_data)

    monkeypatch.setattr("router.tasks.tasks.send_preview_message_to_websocket", fake_send_preview_message_to_websocket)
    monkeypatch.setattr(
        "router.tasks.tasks.ProjectsUseCase",
        type("PU", (), {"get_indexer_database_by_uuid": staticmethod(lambda p: lambda: MagicMock())}),
    )

    trace_events = []
    msg = MagicMock()
    msg.text = "t"
    msg.contact_urn = "u"
    msg.project_uuid = "p"
    event = {"content": {"trace": {"x": 1}}}
    _process_trace_event(
        event=event,
        user_email="user",
        session_id="s",
        project_uuid="p",
        language="en",
        preview=True,
        trace_events=trace_events,
        first_rationale_text=None,
        is_first_rationale=True,
        rationale_history=[],
        should_process_rationales=False,
        message=msg,
        flows_user_email="f",
    )
    assert any(m["type"] == "trace_update" for m in sent)
