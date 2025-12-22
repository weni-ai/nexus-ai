from router.traces_observers.summary import _get_summary_prompt


def test_get_summary_prompt_contains_language_and_json():
    prompt = _get_summary_prompt(language="pt-br", trace_data={"trace": {"modelInvocationInput": {"x": 1}}})
    assert "pt-br" in prompt
    assert "JSON trace to summarize" in prompt
    assert "modelInvocationInput" in prompt
