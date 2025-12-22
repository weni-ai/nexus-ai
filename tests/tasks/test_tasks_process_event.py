from router.tasks.tasks import _process_event


def test_process_event_chunk_appends_and_sends(monkeypatch):
    sent = []

    def fake_send_preview_message_to_websocket(*, project_uuid, user_email, message_data):
        sent.append(message_data)

    monkeypatch.setattr("router.tasks.tasks.send_preview_message_to_websocket", fake_send_preview_message_to_websocket)

    event = {"type": "chunk", "content": "hello "}
    out = _process_event(
        event=event,
        user_email="user",
        session_id="s",
        project_uuid="p",
        language="en",
        preview=True,
        full_response="world",
        trace_events=[],
        first_rationale_text=None,
        is_first_rationale=True,
        rationale_history=[],
        should_process_rationales=False,
        message=None,
        flows_user_email="f",
    )
    assert out == "worldhello "
    assert any(m["type"] == "chunk" for m in sent)
