from router.traces_observers.save_traces import SaveTracesObserver


def test_save_traces_observer_perform_calls_async_task(monkeypatch):
    calls = {}

    def fake_delay(
        *,
        trace_events,
        project_uuid,
        contact_urn,
        agent_response,
        preview,
        session_id,
        source_type,
        contact_name,
        channel_uuid,
    ):
        calls["trace_events"] = trace_events
        calls["project_uuid"] = project_uuid

    monkeypatch.setattr(
        "router.traces_observers.save_traces.save_inline_trace_events",
        type("T", (), {"delay": staticmethod(fake_delay)}),
    )

    obs = SaveTracesObserver()
    obs.perform(
        trace_events=[{"t": 1}, {"t": 2}],
        project_uuid="p",
        contact_urn="u",
        agent_response="resp",
        preview=False,
        session_id="s",
        source_type="router",
        contact_name="n",
        channel_uuid="c",
    )
    assert "trace_events" in calls and calls["project_uuid"] == "p"
