from router.traces_observers.summary import SummaryTracesObserver


def test_summary_traces_observer_preview_sends_trace_update(monkeypatch):
    obs = SummaryTracesObserver()
    sent = {}

    def fake_send_preview_message_to_websocket(*, project_uuid, user_email, message_data):
        sent["project_uuid"] = project_uuid
        sent["user_email"] = user_email
        sent["message_data"] = message_data

    monkeypatch.setattr(
        "nexus.projects.websockets.consumers.send_preview_message_to_websocket", fake_send_preview_message_to_websocket
    )

    obs.perform(
        language="en",
        event_content={"trace": {"x": 1}},
        inline_traces=None,
        preview=True,
        project_uuid="p",
        user_email="u",
        session_id="s",
    )
    assert sent["message_data"]["type"] == "trace_update"
