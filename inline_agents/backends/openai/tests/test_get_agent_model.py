import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from inline_agents.backends.openai.adapter import OpenAIDataLakeEventAdapter
from inline_agents.backends.openai.hooks import _get_agent_model
from inline_agents.data_lake.mock_service import MockDataLakeEventService


class _WhirlpoolModelLike:
    """Stand-in for WhirlpoolModel: Agents SDK Model with a `.model` string id."""

    def __init__(self, model: str):
        self.model = model


class GetAgentModelTests(SimpleTestCase):
    def test_string_model_unchanged(self):
        agent = SimpleNamespace(model="gpt-4.1-mini")
        self.assertEqual(_get_agent_model(agent), "gpt-4.1-mini")

    def test_whirlpool_model_instance_returns_string_id(self):
        agent = SimpleNamespace(model=_WhirlpoolModelLike("custom/whirlpool/generateContent"))
        model_id = _get_agent_model(agent)
        self.assertEqual(model_id, "custom/whirlpool/generateContent")
        self.assertIsInstance(model_id, str)
        json.dumps({"foundation_model": model_id})

    def test_litellm_model_unwraps_model_attr(self):
        class FakeLitellm:
            def __init__(self):
                self.model = "litellm/gemini/gemini-2.0-flash"

        with patch("inline_agents.backends.openai.hooks.LitellmModel", FakeLitellm):
            agent = SimpleNamespace(model=FakeLitellm())
            self.assertEqual(_get_agent_model(agent), "litellm/gemini/gemini-2.0-flash")

    def test_none_model_returns_empty_string(self):
        agent = SimpleNamespace(model=None)
        self.assertEqual(_get_agent_model(agent), "")


class GetAgentModelDataLakeSerializationTests(SimpleTestCase):
    """Whirlpool agent → to_data_lake_event yields a Celery-JSON-serializable payload."""

    def setUp(self):
        self.adapter = OpenAIDataLakeEventAdapter()
        self.mock_service = MockDataLakeEventService()

        def fake_send_validated_event(
            event_data,
            project_uuid,
            contact_urn,
            use_delay=True,
            channel_uuid=None,
            agent_identifier=None,
            conversation=None,
        ):
            # Mimic Celery/kombu: payload must JSON-encode before queueing.
            json.dumps(event_data)
            if use_delay:
                self.mock_service.send_data_lake_event_task.delay(event_data)
            else:
                self.mock_service.send_data_lake_event_task(event_data)
            return event_data

        self.mock_service.send_validated_event = fake_send_validated_event
        self.adapter._event_service = self.mock_service

    def _send_tool_result(self, agent, expected_foundation_model: str) -> dict:
        self.mock_service.clear_events()
        result = self.adapter.to_data_lake_event(
            project_uuid="proj-123",
            contact_urn="urn:test",
            tool_result_data={
                "tool_name": "get_spec",
                "result": {"ok": True},
                "parameters": [],
                "function_name": "get_spec",
            },
            agent_data={"agent_name": "get_spec"},
            foundation_model=_get_agent_model(agent),
            backend="openai",
        )
        self.assertIsNotNone(result)
        self.assertEqual(len(self.mock_service.sent_events_async), 1)
        queued = self.mock_service.sent_events_async[0]
        self.assertEqual(queued["metadata"]["foundation_model"], expected_foundation_model)
        json.dumps(queued)
        return queued

    def test_native_openai_string_model_unchanged_on_datalake_event(self):
        """Native OpenAI: agent.model is already a string; metadata must keep that id."""
        agent = SimpleNamespace(model="gpt-4.1-mini")
        queued = self._send_tool_result(agent, "gpt-4.1-mini")
        self.assertIsInstance(queued["metadata"]["foundation_model"], str)

    def test_litellm_model_unwraps_on_datalake_event(self):
        class FakeLitellm:
            def __init__(self):
                self.model = "litellm/gemini/gemini-2.0-flash"

        with patch("inline_agents.backends.openai.hooks.LitellmModel", FakeLitellm):
            agent = SimpleNamespace(model=FakeLitellm())
            self._send_tool_result(agent, "litellm/gemini/gemini-2.0-flash")

    def test_tool_result_event_with_whirlpool_foundation_model_is_json_serializable(self):
        agent = SimpleNamespace(model=_WhirlpoolModelLike("custom/whirlpool/generateContent"))
        self._send_tool_result(agent, "custom/whirlpool/generateContent")
