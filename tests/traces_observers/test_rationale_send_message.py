from router.traces_observers.rationale_observer import RationaleObserver


def test_rationale_send_message_calls_callback_and_save(monkeypatch):
    calls = {"callback": None, "saved": None}

    def fake_save_inline_message_to_database(**kwargs):
        calls["saved"] = kwargs

    obs = RationaleObserver(bedrock_client=type("B", (), {})(), typing_usecase=type("T", (), {})())

    def cb(**kwargs):
        calls["callback"] = kwargs

    monkeypatch.setattr(
        "router.traces_observers.rationale_observer.save_inline_message_to_database",
        fake_save_inline_message_to_database,
    )
    obs._send_rationale_message(
        text="t",
        contact_urn="u",
        project_uuid="p",
        session_id="s",
        contact_name="n",
        send_message_callback=cb,
        channel_uuid="c",
    )
    assert calls["callback"]["text"] == "t" and calls["saved"]["project_uuid"] == "p"
