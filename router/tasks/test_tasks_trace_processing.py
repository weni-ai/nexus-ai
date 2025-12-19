from unittest.mock import MagicMock

from router.tasks.tasks import _process_trace_event


def test_process_trace_event_preview_sends_trace_update(monkeypatch):
    sent = []

    def fake_send_preview_message_to_websocket(*, project_uuid, user_email, message_data):
        sent.append(message_data)

    monkeypatch.setattr("router.tasks.tasks.send_preview_message_to_websocket", fake_send_preview_message_to_websocket)
    # Patch ProjectsUseCase.get_indexer_database_by_uuid if later code calls it
    monkeypatch.setattr(
        "router.tasks.tasks.ProjectsUseCase",
        type("PU", (), {"get_indexer_database_by_uuid": staticmethod(lambda p: lambda: MagicMock())}),
    )

    trace_events = []
    msg = MagicMock()
    msg.text = "t"
    msg.contact_urn = "u"
    msg.project_uuid = "p"
    event = {"content": {"trace": {"x": 1}}}
    _process_trace_event(
        event=event,
        user_email="user",
        session_id="s",
        project_uuid="p",
        language="en",
        preview=True,
        trace_events=trace_events,
        first_rationale_text=None,
        is_first_rationale=True,
        rationale_history=[],
        should_process_rationales=False,
        message=msg,
        flows_user_email="f",
    )
    assert any(m["type"] == "trace_update" for m in sent)
