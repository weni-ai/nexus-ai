from unittest.mock import MagicMock, patch

import pytest

from router.entities import message_factory
from router.tasks.invoke import (
    _handle_task_error,
    _manage_pending_task,
    _preprocess_message_input,
    dispatch_preview,
    handle_attachments,
    handle_product_items,
)


def test_handle_attachments_appends_or_sets_text():
    t1, off1 = handle_attachments("a", ["file"])
    assert "file" in t1 and off1 is False
    t2, off2 = handle_attachments("", ["file"])
    assert t2 == "['file']" and off2 is True
    t3, off3 = handle_attachments("a", [])
    assert t3 == "a" and off3 is False


def test_handle_product_items_formats_text():
    assert handle_product_items("t", ["p"]) == "t product items: ['p']"
    assert handle_product_items("", ["p"]) == "product items: ['p']"


@patch("router.tasks.invoke.send_preview_message_to_websocket")
@patch("router.tasks.invoke.dispatch")
def test_dispatch_preview_sends_message(dispatch, send_preview):
    msg = message_factory(project_uuid="p", text="t", contact_urn="u")
    out = dispatch_preview(
        "resp", msg, broadcast=MagicMock(), user_email="user", agents_backend="OpenAIBackend", flows_user_email="flows"
    )
    assert out is not None
    dispatch.assert_called_once()
    send_preview.assert_called_once()


def test_preprocess_message_bedrock_calls_complexity_and_handles_items():
    with patch("router.tasks.invoke.complexity_layer") as complexity:
        complexity.return_value = "claude-3"
        msg = {
            "project_uuid": "p",
            "contact_urn": "u",
            "text": "t",
            "attachments": [],
            "metadata": {"order": {"product_items": ["x"]}},
        }
        processed, foundation_model, turn_off = _preprocess_message_input(msg, backend="BedrockBackend")
        assert foundation_model == "claude-3"
        assert "product items" in processed["text"]
        assert turn_off is False


def test_preprocess_message_empty_raises():
    msg = {"project_uuid": "p", "contact_urn": "u", "text": " ", "attachments": []}
    with pytest.raises(Exception):
        _preprocess_message_input(msg, backend="OpenAIBackend")


def test_preprocess_message_attachments_turn_off_rationale():
    msg = {"project_uuid": "p", "contact_urn": "u", "text": "", "attachments": ["a.pdf"]}
    processed, foundation_model, turn_off = _preprocess_message_input(msg, backend="OpenAIBackend")
    assert "['a.pdf']" in processed["text"]
    assert foundation_model is None
    assert turn_off is True


def test_manage_pending_task_stores_and_returns_final_text(monkeypatch):
    class TM:
        def __init__(self):
            self.stored = []

        def get_pending_task_id(self, project_uuid, contact_urn):
            return None

        def handle_pending_response(self, project_uuid, contact_urn, message_text):
            return message_text + " [pending]"

        def store_pending_task_id(self, project_uuid, contact_urn, task_id):
            self.stored.append((project_uuid, contact_urn, task_id))

    msg = message_factory(project_uuid="p", text="hello", contact_urn="u")
    tm = TM()
    out = _manage_pending_task(tm, msg, current_task_id="id1")
    assert out.endswith("[pending]")
    assert tm.stored[0] == ("p", "u", "id1")


@patch("router.tasks.invoke.send_preview_message_to_websocket")
@patch("router.tasks.invoke.sentry_sdk.capture_exception")
def test_handle_task_error_sends_preview_and_raises(capture_exception, send_preview):
    class TM:
        def clear_pending_tasks(self, project_uuid, contact_urn):
            pass

        def get_pending_task_id(self, project_uuid, contact_urn):
            return "old"

    msg = {"project_uuid": "p", "contact_urn": "u", "text": "t", "msg_event": {"msg_external_id": "e"}}
    with pytest.raises(Exception):
        _handle_task_error(Exception("x"), TM(), msg, task_id="id2", preview=True, language="en", user_email="user")
    send_preview.assert_called_once()
    capture_exception.assert_called_once()
