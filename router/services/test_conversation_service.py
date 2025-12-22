from unittest.mock import MagicMock, patch

import pytest

from router.services.conversation_service import ConversationService


def test_create_conversation_if_channel_exists_none_channel_logs_and_returns_none():
    svc = ConversationService()
    with patch("router.services.conversation_service.sentry_sdk.set_tag") as set_tag, patch(
        "router.services.conversation_service.sentry_sdk.set_context"
    ) as set_context, patch("router.services.conversation_service.sentry_sdk.capture_message") as capture_message:
        result = svc.create_conversation_if_channel_exists(
            project_uuid="p", contact_urn="u", contact_name="n", channel_uuid=None
        )
        assert result is None
        assert set_tag.call_count >= 2
        assert set_context.call_count == 1
        assert capture_message.call_count == 1


def test_create_conversation_if_channel_exists_with_channel_calls_usecase():
    svc = ConversationService()
    svc.conversation_usecase = MagicMock()
    svc.conversation_usecase.create_conversation_base_structure.return_value = {"ok": True}
    result = svc.create_conversation_if_channel_exists(
        project_uuid="p", contact_urn="u", contact_name="n", channel_uuid="c"
    )
    assert result == {"ok": True}
    svc.conversation_usecase.create_conversation_base_structure.assert_called_once()


def test_ensure_conversation_exists_none_channel_logs_and_returns_none():
    svc = ConversationService()
    with patch("router.services.conversation_service.sentry_sdk.set_tag") as set_tag, patch(
        "router.services.conversation_service.sentry_sdk.set_context"
    ) as set_context, patch("router.services.conversation_service.sentry_sdk.capture_message") as capture_message:
        result = svc.ensure_conversation_exists(project_uuid="p", contact_urn="u", contact_name="n", channel_uuid=None)
        assert result is None
        assert set_tag.call_count >= 2
        assert set_context.call_count == 1
        assert capture_message.call_count == 1


def test_ensure_conversation_exists_with_channel_calls_usecase():
    svc = ConversationService()
    svc.conversation_usecase = MagicMock()
    svc.conversation_usecase.conversation_in_progress_exists.return_value = {"exists": True}
    result = svc.ensure_conversation_exists(project_uuid="p", contact_urn="u", contact_name="n", channel_uuid="c")
    assert result == {"exists": True}
    svc.conversation_usecase.conversation_in_progress_exists.assert_called_once()


def test_ensure_conversation_exists_exception_path_logs_and_reraises():
    svc = ConversationService()
    svc.conversation_usecase = MagicMock()
    svc.conversation_usecase.conversation_in_progress_exists.side_effect = Exception("x")
    with patch("router.services.conversation_service.sentry_sdk.capture_exception") as capture_exception:
        with pytest.raises(Exception):
            svc.ensure_conversation_exists(project_uuid="p", contact_urn="u", contact_name="n", channel_uuid="c")
        assert capture_exception.call_count == 1
