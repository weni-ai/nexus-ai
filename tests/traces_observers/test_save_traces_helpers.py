from router.traces_observers.save_traces import _prepare_trace_data, trace_events_to_json


def test_prepare_trace_data_and_trace_events_to_json():
    data = _prepare_trace_data([{"a": 1}, {"b": 2}])
    assert '"a": 1' in data and '"b": 2' in data
    assert trace_events_to_json({"x": "y"}).startswith("{")
