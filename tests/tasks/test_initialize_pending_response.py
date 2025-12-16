import types


def test_initialize_and_handle_pending_response(monkeypatch):
    from router.tasks.tasks import _initialize_and_handle_pending_response

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

    dummy = DummyRedis()
    dummy.store["multi_response:u"] = "prev"
    dummy.store["multi_task:u"] = "old"

    monkeypatch.setattr("router.tasks.tasks.Redis", types.SimpleNamespace(from_url=lambda url: dummy))
    monkeypatch.setattr(
        "router.tasks.tasks.celery_app",
        types.SimpleNamespace(control=types.SimpleNamespace(revoke=lambda *_a, **_k: None)),
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
    assert "multi_response:u" not in dummy.store
    assert dummy.store["multi_task:u"] == "newtask"
