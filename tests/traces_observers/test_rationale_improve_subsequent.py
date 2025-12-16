from router.traces_observers.rationale_observer import RationaleObserver


def test_rationale_improve_subsequent(monkeypatch):
    class DummyBedrock:
        def converse(self, **kwargs):
            return {"output": {"message": {"content": [{"text": "Improved"}]}}}

    obs = RationaleObserver(bedrock_client=DummyBedrock(), typing_usecase=type("T", (), {})())
    out = obs._improve_subsequent_rationale("raw", previous_rationales=["a", "b"], user_input="u")
    assert out == "Improved"
