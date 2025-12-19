import json

from router.repositories.redis.message import MessageRepository


class FakeRedis:
    def __init__(self):
        self.store = {}

    def setex(self, key, ttl, value):
        self.store[key] = (ttl, value)

    def get(self, key):
        v = self.store.get(key)
        if not v:
            return None
        return v[1].encode("utf-8") if isinstance(v[1], str) else v[1]

    def delete(self, key):
        if key in self.store:
            del self.store[key]


def test_storage_and_get_messages_with_limit():
    r = FakeRedis()
    repo = MessageRepository(r)
    repo.storage_message(
        project_uuid="p",
        contact_urn="u",
        message_data={"text": "t", "source": "s", "created_at": "now"},
        channel_uuid=None,
        ttl_hours=1,
    )
    resp = repo.get_messages(project_uuid="p", contact_urn="u", channel_uuid=None, limit=1)
    assert resp["items"][0]["text"] == "t"
    assert resp["total_count"] == 1


def test_get_messages_empty_returns_defaults():
    r = FakeRedis()
    repo = MessageRepository(r)
    resp = repo.get_messages(project_uuid="p", contact_urn="u", channel_uuid=None)
    assert resp == {"items": [], "next_cursor": None, "total_count": 0}


def test_add_message_appends_and_persists():
    r = FakeRedis()
    repo = MessageRepository(r)
    repo.storage_message(
        project_uuid="p",
        contact_urn="u",
        message_data={"text": "t", "source": "s", "created_at": "now"},
        channel_uuid=None,
        ttl_hours=1,
    )
    repo.add_message("p", "u", {"text": "t2", "source": "s", "created_at": "later"})
    stored = json.loads(r.get("conversation:p:u").decode("utf-8"))
    assert len(stored) == 2
    assert stored[1]["text"] == "t2"


def test_delete_messages_clears_store():
    r = FakeRedis()
    repo = MessageRepository(r)
    repo.storage_message(
        project_uuid="p",
        contact_urn="u",
        message_data={"text": "t", "source": "s", "created_at": "now"},
        channel_uuid=None,
        ttl_hours=1,
    )
    repo.delete_messages("p", "u")
    assert r.get("conversation:p:u") is None


def test_store_batch_messages_merges_existing_list():
    r = FakeRedis()
    repo = MessageRepository(r)
    repo.store_batch_messages("p", "u", [{"text": "a"}], key="batch")
    repo.store_batch_messages("p", "u", [{"text": "b"}], key="batch")
    stored = json.loads(r.get("batch:p:u").decode("utf-8"))
    assert stored == [{"text": "a"}, {"text": "b"}]
