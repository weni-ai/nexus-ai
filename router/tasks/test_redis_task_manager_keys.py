from router.tasks.redis_task_manager import RedisTaskManager


def test_redis_task_manager_pending_keys(monkeypatch):
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
    manager = RedisTaskManager(redis_client=dummy)

    # Store and read task id
    manager.store_pending_task_id("p", "u", "tid")
    assert manager.get_pending_task_id("p", "u") == "tid"

    # Store and read response
    manager.store_pending_response("p", "u", "resp")
    assert manager.get_pending_response("p", "u") == "resp"

    # Clear
    manager.clear_pending_tasks("p", "u")
    assert manager.get_pending_task_id("p", "u") is None
    assert manager.get_pending_response("p", "u") is None
