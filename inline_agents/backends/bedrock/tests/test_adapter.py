from django.test import TestCase
from unittest.mock import Mock

from inline_agents.backends.bedrock.adapter import BedrockDataLakeEventAdapter
from inline_agents.backends.bedrock.tests.traces_factory import (
    ActionGroupTraceFactory,
    AgentCollaborationTraceFactory
)


def mock_send_data_lake_event_task(
    event_data: dict
):
    pass


class TestBedrockDataLakeEventAdapter(TestCase):
    def setUp(self):
        self.mock_send_data_lake_event_task = Mock()
        self.adapter = BedrockDataLakeEventAdapter(
            send_data_lake_event_task=self.mock_send_data_lake_event_task
        )
        self.project_uuid = "test-project-uuid"
        self.contact_urn = "tel:1234567890"

    def test_to_data_lake_event_with_action_group(self):
        action_group_trace = ActionGroupTraceFactory()

        event_data = self.adapter.to_data_lake_event(
            inline_trace=action_group_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn
        )

        self.assertEqual(event_data["event_name"], "action_group")
        self.assertEqual(event_data["key"], "trace")
        self.assertEqual(event_data["project"], self.project_uuid)
        self.assertEqual(event_data["contact_urn"], self.contact_urn)
        self.assertEqual(event_data["value_type"], "string")
        self.assertEqual(event_data["value"], "teste")
        self.assertIn("action_group", event_data["metadata"])
        self.assertTrue(event_data["metadata"]["action_group"])

    def test_to_data_lake_event_with_agent_collaboration(self):
        agent_trace = AgentCollaborationTraceFactory()

        event_data = self.adapter.to_data_lake_event(
            inline_trace=agent_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn
        )

        self.assertEqual(event_data["event_name"], "agent_invocation")
        self.assertEqual(event_data["key"], "trace")
        self.assertEqual(event_data["project"], self.project_uuid)
        self.assertEqual(event_data["contact_urn"], self.contact_urn)
        self.assertEqual(event_data["value_type"], "string")
        self.assertEqual(event_data["value"], "teste")
        self.assertIn("agent_collaboration", event_data["metadata"])
        self.assertTrue(event_data["metadata"]["agent_collaboration"])

    def test_metadata_action_group(self):
        action_group_input = {
            "actionGroupName": "test_action_group",
            "function": "test_function",
            "parameters": [
                {
                    "name": "test_param",
                    "type": "string",
                    "value": "test_value"
                }
            ]
        }

        metadata = self.adapter.metadata_action_group(action_group_input)

        self.assertEqual(metadata["action_group_name"], "test_action_group")
        self.assertEqual(metadata["function_name"], "test_function")
        self.assertEqual(metadata["parameters"], action_group_input["parameters"])

    def test_metadata_agent_collaboration(self):
        agent_collaboration_input = {
            "agentCollaboratorName": "test_agent",
            "input": {
                "text": "test input text",
                "type": "TEXT"
            }
        }

        metadata = self.adapter.metadata_agent_collaboration(agent_collaboration_input)

        self.assertEqual(metadata["agent_name"], "test_agent")
        self.assertEqual(metadata["input_text"], "test input text")
