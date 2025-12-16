from router.tasks.tasks import _process_trace_event


def test_process_trace_event_error_sends_error(monkeypatch):
    sent = []

    def fake_send_preview_message_to_websocket(*, project_uuid, user_email, message_data):
        sent.append(message_data)

    def fake_get_trace_summary(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("router.tasks.tasks.send_preview_message_to_websocket", fake_send_preview_message_to_websocket)
    monkeypatch.setattr("router.tasks.tasks.get_trace_summary", fake_get_trace_summary)

    event = {"type": "trace", "content": {"trace": {"orchestrationTrace": {"rationale": {"text": "x"}}}}}
    _process_trace_event(
        event=event,
        user_email="user",
        session_id="s",
        project_uuid="p",
        language="en",
        preview=False,
        trace_events=[],
        first_rationale_text=None,
        is_first_rationale=True,
        rationale_history=[],
        should_process_rationales=True,
        message=type("M", (), {"text": "t", "contact_urn": "u"})(),
        flows_user_email="f",
    )

    assert any(m["type"] == "error" and "boom" in m["content"] for m in sent)
