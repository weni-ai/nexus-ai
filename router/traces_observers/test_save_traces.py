from router.traces_observers.save_traces import _prepare_trace_data, trace_events_to_json


def test_trace_events_to_json_serializes_with_default_str():
    ev = {"ts": "2024-01-01T00:00:00Z", "a": 1}
    out = trace_events_to_json(ev)
    assert '"a": 1' in out


def test_prepare_trace_data_concatenates_lines():
    events = [{"a": 1}, {"b": 2}]
    data = _prepare_trace_data(events)
    assert '"a": 1' in data and '"b": 2' in data
    assert data.count("\n") >= 2
