from router.tasks.tasks import trace_events_to_json


def test_trace_events_to_json_outputs_json_string():
    s = trace_events_to_json({"a": 1})
    assert s.startswith("{") and '"a": 1' in s
