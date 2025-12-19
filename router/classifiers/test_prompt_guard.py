from unittest.mock import patch

from router.classifiers.prompt_guard import PromptGuard


@patch("router.classifiers.prompt_guard.requests.request")
def test_prompt_guard_classify_injection_false(mock_req, monkeypatch):
    monkeypatch.setenv("PROMPT_GUARD_URL", "http://pg")
    monkeypatch.setenv("PROMPT_GUARD_API_KEY", "key")
    monkeypatch.setenv("USE_PROMPT_GUARD", "true")
    mock_req.return_value.json.return_value = {"output": {"guardrails_classification": "injection"}}
    pg = PromptGuard()
    assert pg.classify("msg") is False


@patch("router.classifiers.prompt_guard.requests.request")
def test_prompt_guard_classify_non_injection_true(mock_req, monkeypatch):
    monkeypatch.setenv("PROMPT_GUARD_URL", "http://pg")
    monkeypatch.setenv("PROMPT_GUARD_API_KEY", "key")
    monkeypatch.setenv("USE_PROMPT_GUARD", "true")
    mock_req.return_value.json.return_value = {"output": {"guardrails_classification": "clean"}}
    pg = PromptGuard()
    assert pg.classify("msg") is True


def test_prompt_guard_disabled_returns_true(monkeypatch):
    monkeypatch.setenv("USE_PROMPT_GUARD", "false")
    pg = PromptGuard()
    assert pg.classify("msg") is True
