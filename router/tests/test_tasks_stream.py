from router.tasks.tasks import _process_event, _process_trace_event


def test_process_event_chunk_sends_accumulates(monkeypatch):
    sent = {"called": False}

    def fake_send_preview_message_to_websocket(**kwargs):
        sent["called"] = True

    monkeypatch.setattr("router.tasks.tasks.send_preview_message_to_websocket", fake_send_preview_message_to_websocket)
    full = _process_event(
        event={"type": "chunk", "content": "A"},
        user_email="u",
        session_id="s",
        project_uuid="p",
        language="en",
        preview=True,
        full_response="",
        trace_events=[],
        first_rationale_text=None,
        is_first_rationale=True,
        rationale_history=[],
        should_process_rationales=False,
        message=None,
        flows_user_email="flows",
    )
    assert full == "A"
    assert sent["called"] is True


def test_process_trace_event_summary_and_append(monkeypatch):
    sent = {"count": 0}

    def fake_send_preview_message_to_websocket(**kwargs):
        sent["count"] += 1

    def fake_get_trace_summary(language, content):
        return "Summary"

    monkeypatch.setattr("router.tasks.tasks.send_preview_message_to_websocket", fake_send_preview_message_to_websocket)
    monkeypatch.setattr("router.tasks.tasks.get_trace_summary", fake_get_trace_summary)
    ev = {"type": "trace", "content": {"a": 1}}
    traces = []
    _process_trace_event(
        event=ev,
        user_email="u",
        session_id="s",
        project_uuid="p",
        language="en",
        preview=True,
        trace_events=traces,
        first_rationale_text=None,
        is_first_rationale=True,
        rationale_history=[],
        should_process_rationales=False,
        message=None,
        flows_user_email="flows",
    )
    assert traces and traces[0]["a"] == 1
    assert ev["content"]["summary"] == "Summary"
    assert sent["count"] >= 1
