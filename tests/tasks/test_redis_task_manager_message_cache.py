from router.tasks.redis_task_manager import RedisTaskManager


def test_redis_task_manager_handle_message_cache(monkeypatch):
    calls = {"created": False, "added": False}

    class DummyRepo:
        def __init__(self, client):
            self.client = client
            self.messages = []

        def get_messages(self, project_uuid, contact_urn):
            return self.messages

        def storage_message(self, project_uuid, contact_urn, message_data):
            calls["created"] = True
            self.messages.append(message_data)

        def add_message(self, project_uuid, contact_urn, message):
            calls["added"] = True
            self.messages.append(message)

        def delete_messages(self, project_uuid, contact_urn):
            self.messages = []

    class DummyConv:
        def create_conversation_if_channel_exists(self, **kwargs):
            pass

        def ensure_conversation_exists(self, **kwargs):
            pass

    class DummyRedis:
        def set(self, *args, **kwargs):
            pass

    monkeypatch.setattr("router.tasks.redis_task_manager.RedisMessageRepository", lambda client: DummyRepo(client))
    manager = RedisTaskManager(redis_client=DummyRedis())
    monkeypatch.setattr("router.services.conversation_service.ConversationService", lambda: DummyConv())

    # First call should create initial message storage
    manager.handle_message_cache(
        contact_urn="u",
        contact_name="n",
        project_uuid="p",
        msg_text="first",
        source="router",
        channel_uuid="c",
        preview=False,
    )
    assert calls["created"] is True and calls["added"] is False

    # Second call should add message to existing cache
    manager.handle_message_cache(
        contact_urn="u",
        contact_name="n",
        project_uuid="p",
        msg_text="second",
        source="router",
        channel_uuid="c",
        preview=False,
    )
    assert calls["added"] is True
