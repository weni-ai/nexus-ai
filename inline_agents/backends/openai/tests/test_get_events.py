from unittest.mock import patch

from django.test import SimpleTestCase

from inline_agents.backends.openai.entities import HooksState
from inline_agents.backends.openai.hooks import _get_events_from_tool_result


class GetEventsTests(SimpleTestCase):
    def test_string_result_returns_empty_list(self):
        state = HooksState(agents=[])
        self.assertEqual(state.get_events("Aguarde um momento", "iniciaratendimentohumano"), [])

    def test_dict_result_returns_events(self):
        state = HooksState(agents=[])
        events = [{"event_name": "weni_nexus_data"}]
        self.assertEqual(state.get_events({"events": events}, "tool"), events)

    def test_session_events_take_precedence_over_result(self):
        state = HooksState(agents=[])
        session_events = [{"event_name": "from_session"}]
        state.add_tool_info("tool", {"events": session_events})
        self.assertEqual(state.get_events("Aguarde um momento", "tool"), session_events)

    def test_list_of_dicts_returns_events(self):
        state = HooksState(agents=[])
        result = [{"events": [{"event_name": "a"}]}, "skip", {"events": [{"event_name": "b"}]}]
        self.assertEqual(
            state.get_events(result, "tool"),
            [{"event_name": "a"}, {"event_name": "b"}],
        )

    def test_json_null_number_and_bool_return_empty_list(self):
        state = HooksState(agents=[])
        for value in (None, 0, 1, True, False):
            self.assertEqual(state.get_events(value, "tool"), [])

    def test_dict_without_events_key_returns_empty_list(self):
        state = HooksState(agents=[])
        self.assertEqual(state.get_events({"result": "ok"}, "tool"), [])

    def test_list_item_with_non_list_events_is_skipped(self):
        state = HooksState(agents=[])
        result = [
            {"events": "abc"},
            {"events": None},
            {"events": {"event_name": "nested"}},
            {"other": True},
            {"events": [{"event_name": "kept"}]},
        ]
        self.assertEqual(state.get_events(result, "tool"), [{"event_name": "kept"}])

    def test_json_string_tool_result_does_not_report_to_sentry(self):
        state = HooksState(agents=[])
        with patch("inline_agents.backends.openai.hooks.sentry_sdk.capture_exception") as capture:
            events = _get_events_from_tool_result(
                '"Aguarde um momento"',
                "iniciaratendimentohumano",
                state,
                "project-uuid",
                "whatsapp:5500000000000",
            )
        self.assertEqual(events, [])
        capture.assert_not_called()
