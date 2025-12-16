from router.traces_observers.rationale_observer import RationaleObserver


def test_rationale_validity_and_accents():
    obs = RationaleObserver(bedrock_client=type("B", (), {})(), typing_usecase=type("T", (), {})())
    assert obs._is_valid_rationale("Válido") is True
    assert obs._is_valid_rationale("invalid reason") is False
