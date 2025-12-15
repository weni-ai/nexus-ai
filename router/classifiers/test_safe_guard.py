from unittest.mock import patch

from router.classifiers.safe_guard import SafeGuard


@patch("router.classifiers.safe_guard.requests.request")
def test_safe_guard_classify_safe_true(mock_req, monkeypatch):
    monkeypatch.setenv("SAFEGUARD_URL", "http://sg")
    monkeypatch.setenv("SAFEGUARD_PROMPT", "prompt {{question}}")
    monkeypatch.setenv("SAFEGUARD_COOKIE", "cookie")
    monkeypatch.setenv("SAFEGUARD_API_KEY", "key")
    monkeypatch.setenv("USE_SAFEGUARD", "true")
    mock_req.return_value.json.return_value = {"output": [{"choices": [{"tokens": ["safe"]}]}]}
    sg = SafeGuard()
    assert sg.classify("msg") is True


@patch("router.classifiers.safe_guard.requests.request")
def test_safe_guard_classify_unsafe_false(mock_req, monkeypatch):
    monkeypatch.setenv("SAFEGUARD_URL", "http://sg")
    monkeypatch.setenv("SAFEGUARD_PROMPT", "prompt {{question}}")
    monkeypatch.setenv("SAFEGUARD_COOKIE", "cookie")
    monkeypatch.setenv("SAFEGUARD_API_KEY", "key")
    monkeypatch.setenv("USE_SAFEGUARD", "true")
    mock_req.return_value.json.return_value = {"output": [{"choices": [{"tokens": ["unsafe"]}]}]}
    sg = SafeGuard()
    assert sg.classify("msg") is False


def test_safe_guard_disabled_returns_true(monkeypatch):
    monkeypatch.setenv("USE_SAFEGUARD", "false")
    sg = SafeGuard()
    assert sg.classify("msg") is True
