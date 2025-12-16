from router.tasks.redis_task_manager import RedisTaskManager


def test_rabbitmq_msg_batch_to_cache(monkeypatch):
    class DummyRedis:
        def __init__(self):
            self.store = {}

        def get(self, k):
            v = self.store.get(k)
            return v.encode("utf-8") if isinstance(v, str) else None

        def setex(self, k, ttl, v):
            self.store[k] = v

    class DummyRepo:
        def __init__(self, client):
            self.client = client

        def store_batch_messages(self, project_uuid, contact_urn, messages, key):
            self.client.setex(f"{key}:{project_uuid}:{contact_urn}", 172800, "stored")

    dummy = DummyRedis()
    monkeypatch.setattr("router.tasks.redis_task_manager.RedisMessageRepository", lambda client: DummyRepo(client))
    manager = RedisTaskManager(redis_client=dummy)
    manager.rabbitmq_msg_batch_to_cache("p", "u", [{"t": 1}], "k")
    assert dummy.store["k:p:u"] == "stored"
