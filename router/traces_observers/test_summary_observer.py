from router.traces_observers.summary import SummaryTracesObserver


def test_summary_observer_preview_sends_trace(monkeypatch):
    sent = {"called": False}

    def fake_send_preview_message_to_websocket(**kwargs):
        sent["called"] = True

    monkeypatch.setattr(
        "nexus.projects.websockets.consumers.send_preview_message_to_websocket",
        fake_send_preview_message_to_websocket,
    )
    obs = SummaryTracesObserver()
    obs.perform(
        language="en",
        inline_traces={"trace": {"modelInvocationInput": {}}},
        preview=True,
        project_uuid="p",
        user_email="u",
        session_id="s",
    )
    assert sent["called"] is True
