from router.traces_observers.rationale.observer import RationaleObserver


def test_rationale_observer_perform_preview_sends_typing_and_store_message(monkeypatch):
    typing_called = {"called": False}
    saved = {"called": False}

    class FakeTypingUsecase:
        @staticmethod
        def send_typing_message(*args, **kwargs):
            typing_called["called"] = True

    def fake_save_inline_message_to_database(**kwargs):
        saved["called"] = True
        return type("M", (), {"uuid": "x"})

    class StubManager:
        def get_rationale_session_data(self, session_id):
            return {"is_first_rationale": True, "rationale_history": [], "first_rationale_text": ""}

        def save_rationale_session_data(self, session_id, data):
            pass

    monkeypatch.setattr("router.traces_observers.rationale.observer.TypingUsecase", FakeTypingUsecase)
    monkeypatch.setattr(
        "router.traces_observers.save_traces.save_inline_message_to_database",
        fake_save_inline_message_to_database,
    )
    monkeypatch.setattr(
        "router.traces_observers.rationale.observer.RationaleObserver._get_redis_task_manager",
        lambda self: StubManager(),
    )
    monkeypatch.setattr(
        "router.traces_observers.rationale.observer.RationaleObserver._handle_preview_message",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "router.traces_observers.rationale.observer.SendMessageHTTPClient",
        type("C", (), {"__init__": lambda *a, **k: None, "send_direct_message": lambda *a, **k: None}),
    )

    obs = RationaleObserver()
    obs.perform(
        language="en",
        inline_traces={
            "trace": {
                "orchestrationTrace": {
                    "rationale": {"text": "thinking"},
                    "invocationInput": {"agentCollaboratorInvocationInput": {}},
                }
            }
        },
        preview=True,
        project_uuid="p",
        user_email="u",
        session_id="s",
        message_external_id="external-id",
        contact_urn="urn",
        contact_name="name",
        channel_uuid="c",
        rationale_switch=True,
    )
    assert typing_called["called"] is True
    assert saved["called"] is True
