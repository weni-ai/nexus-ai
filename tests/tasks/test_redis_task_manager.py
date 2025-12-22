from unittest.mock import MagicMock

from router.tasks.redis_task_manager import RedisTaskManager


class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        v = self.store.get(key)
        return v.encode("utf-8") if isinstance(v, str) else v

    def set(self, key, value):
        self.store[key] = value

    def setex(self, key, ttl, value):
        self.store[key] = value

    def delete(self, key):
        if key in self.store:
            del self.store[key]


def test_handle_pending_response_concatenates_or_stores_new():
    tm = RedisTaskManager(redis_client=FakeRedis())
    # First store
    out1 = tm.handle_pending_response("p", "u", "first")
    assert out1 == "first"
    # Second concatenates
    out2 = tm.handle_pending_response("p", "u", "second")
    assert out2 == "first\nsecond"


def test_clear_pending_tasks_deletes_keys():
    r = FakeRedis()
    tm = RedisTaskManager(redis_client=r)
    tm.store_pending_response("p", "u", "msg")
    tm.store_pending_task_id("p", "u", "tid")
    tm.clear_pending_tasks("p", "u")
    assert r.get("response:p:u") is None
    assert r.get("task:p:u") is None


def test_create_and_add_message_to_cache_calls_conversation_service():
    r = FakeRedis()
    tm = RedisTaskManager(redis_client=r)
    tm._conversation_service = MagicMock()
    tm.create_message_to_cache("t", "u", "n", "p", "s", channel_uuid="c")
    tm._conversation_service.create_conversation_if_channel_exists.assert_called_once()
    tm.add_message_to_cache("p", "u", "t", "s", channel_uuid="c", contact_name="n")
    tm._conversation_service.ensure_conversation_exists.assert_called_once()
