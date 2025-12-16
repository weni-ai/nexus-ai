from router.traces_observers.summary import _update_trace_summary


def test_update_trace_summary_calls_openai(monkeypatch):
    class DummyCompletions:
        @staticmethod
        def create(**kwargs):
            class R:
                choices = [type("C", (), {"message": type("M", (), {"content": "Summary"})()})()]

            return R()

    class DummyChat:
        completions = DummyCompletions()

    class DummyClient:
        def __init__(self):
            self.chat = DummyChat()

    monkeypatch.setattr("router.traces_observers.summary.OpenAI", lambda: DummyClient())
    out = _update_trace_summary("en", {"x": 1})
    assert out == "Summary"
