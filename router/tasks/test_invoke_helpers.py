from unittest.mock import MagicMock

import pytest

from router.tasks.invoke import _manage_pending_task, handle_attachments


def test_handle_attachments_appends_to_text():
    text, turn_off = handle_attachments("hello", ["file1"])
    assert "file1" in text and turn_off is False


def test_handle_attachments_turns_off_rationale_when_no_text():
    text, turn_off = handle_attachments("", ["file1"])
    assert text == "['file1']" and turn_off is True


@pytest.mark.django_db
def test_manage_pending_task_revokes_and_concatenates(monkeypatch):
    class StubTaskManager:
        def __init__(self):
            self.pending_task_id = "old-id"
            self.stored = None

        def get_pending_task_id(self, project_uuid, contact_urn):
            return self.pending_task_id

        def handle_pending_response(self, project_uuid, contact_urn, message_text):
            return "old\n" + message_text

        def store_pending_task_id(self, project_uuid, contact_urn, current_task_id):
            self.stored = current_task_id

    revoked = {"called": False, "id": None}
    monkeypatch.setattr(
        "router.tasks.invoke.celery_app",
        type(
            "C",
            (),
            {
                "control": type(
                    "X", (), {"revoke": staticmethod(lambda tid, terminate: revoked.update(called=True, id=tid))}
                )
            },
        )(),
    )

    task_manager = StubTaskManager()
    msg = MagicMock()
    msg.project_uuid = "p"
    msg.contact_urn = "u"
    msg.text = "new"
    out = _manage_pending_task(task_manager, msg, current_task_id="new-id")
    assert out == "old\nnew"
    assert revoked["called"] is True and revoked["id"] == "old-id"
    assert task_manager.stored == "new-id"
