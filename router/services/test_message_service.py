from unittest.mock import MagicMock

from router.services.message_service import MessageService


def test_handle_message_cache_creates_or_adds_based_on_existing():
    repo = MagicMock()
    svc = MessageService(message_repository=repo)
    # No channel -> returns early
    svc.handle_message_cache("u", "n", "p", "t", "s", channel_uuid=None, preview=False)
    repo.get_messages.assert_not_called()
    # With channel but no existing messages -> create
    repo.get_messages.return_value = {"items": []}
    svc.handle_message_cache(
        "u", "n", "p", "t", "s", channel_uuid="00000000-0000-0000-0000-000000000000", preview=False
    )
    repo.storage_message.assert_called_once()
    # Now existing messages -> add
    repo.storage_message.reset_mock()
    repo.get_messages.return_value = {"items": [{"text": "prior"}]}
    svc._conversation_service = MagicMock()
    svc.handle_message_cache(
        "u", "n", "p", "t", "s", channel_uuid="00000000-0000-0000-0000-000000000000", preview=False
    )
    repo.add_message.assert_called_once()


def test_add_message_to_cache_ensures_conversation():
    repo = MagicMock()
    svc = MessageService(message_repository=repo)
    conv = MagicMock()
    svc._conversation_service = conv
    svc.add_message_to_cache("p", "u", "t", "s", channel_uuid="c", contact_name="n")
    conv.ensure_conversation_exists.assert_called_once()
