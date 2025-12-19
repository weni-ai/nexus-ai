import pytest

from router.tasks.tasks import save_trace_events


@pytest.mark.django_db
def test_save_trace_events_uploads(monkeypatch):
    uploaded = {}

    def fake_upload_traces(data, key):
        uploaded["data"] = data
        uploaded["key"] = key

    monkeypatch.setattr(
        "router.tasks.tasks.BedrockFileDatabase", type("B", (), {"upload_traces": staticmethod(fake_upload_traces)})
    )
    monkeypatch.setattr(
        "router.tasks.tasks.AgentMessage",
        type(
            "M", (), {"objects": type("O", (), {"create": staticmethod(lambda **k: type("MM", (), {"uuid": "u"})())})()}
        ),
    )

    save_trace_events(
        trace_events=[{"t": 1}, {"t": 2}],
        project_uuid="p",
        team_id="tid",
        user_text="u",
        contact_urn="urn",
        agent_response="resp",
        preview=False,
        session_id="s",
    )

    assert uploaded["key"].startswith("traces/p/")
    assert "t" in uploaded["data"]
