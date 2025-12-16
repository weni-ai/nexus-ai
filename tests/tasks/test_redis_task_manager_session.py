import json

from router.tasks.redis_task_manager import RedisTaskManager


def test_redis_task_manager_session_data(monkeypatch):
    class DummyRedis:
        def __init__(self):
            self.store = {}

        def get(self, k):
            v = self.store.get(k)
            if v is None:
                return None
            return v.encode("utf-8")

        def setex(self, k, ttl, v):
            self.store[k] = v

    dummy = DummyRedis()
    manager = RedisTaskManager(redis_client=dummy)
    session = manager.get_rationale_session_data("sess")
    assert (
        session["rationale_history"] == [] and session["first_rationale_text"] is None and session["is_first_rationale"]
    )

    session["rationale_history"].append("a")
    manager.save_rationale_session_data("sess", session)
    out = json.loads(dummy.store["rationale_session_sess"])
    assert out["rationale_history"] == ["a"]
