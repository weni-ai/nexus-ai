from django.test import TestCase
from unittest.mock import Mock

from inline_agents.backends.bedrock.adapter import BedrockDataLakeEventAdapter
from inline_agents.backends.bedrock.tests.traces_factory import (
    ActionGroupTraceFactory,
    AgentCollaborationTraceFactory,
    CustomEventTraceFactory
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

        self.assertEqual(event_data["event_name"], "weni_nexus_data")
        self.assertEqual(event_data["key"], "tool_call")
        self.assertEqual(event_data["project"], self.project_uuid)
        self.assertEqual(event_data["contact_urn"], self.contact_urn)
        self.assertEqual(event_data["value_type"], "string")
        self.assertEqual(event_data["value"], event_data["metadata"]["tool_call"]["tool_name"])
        self.assertIn("tool_call", event_data["metadata"])

    def test_to_data_lake_event_with_agent_collaboration(self):
        agent_trace = AgentCollaborationTraceFactory()

        event_data = self.adapter.to_data_lake_event(
            inline_trace=agent_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn
        )

        self.assertEqual(event_data["event_name"], "weni_nexus_data")
        self.assertEqual(event_data["key"], "agent_invocation")
        self.assertEqual(event_data["project"], self.project_uuid)
        self.assertEqual(event_data["contact_urn"], self.contact_urn)
        self.assertEqual(event_data["value_type"], "string")
        self.assertEqual(event_data["value"], event_data["metadata"]["agent_collaboration"]["agent_name"])
        self.assertIn("agent_collaboration", event_data["metadata"])

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

        self.assertEqual(metadata["tool_name"], "test_action_group")
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

    def test_custom_event_data_with_valid_trace(self):
        """Test custom_event_data method with a valid CustomEventTraceFactory trace"""
        custom_trace = CustomEventTraceFactory()

        # Call the method
        self.adapter.custom_event_data(
            inline_trace=custom_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn
        )

        # Verify the mock was called with the expected event data
        self.mock_send_data_lake_event_task.delay.assert_called_once()

        # Get the call arguments
        call_args = self.mock_send_data_lake_event_task.delay.call_args[0][0]

        # Verify the event data structure
        self.assertEqual(call_args["event_name"], "weni_nexus_data")
        self.assertEqual(call_args["key"], "csat")
        self.assertEqual(call_args["value_type"], "string")
        self.assertEqual(call_args["value"], "protocol_agent_csat")
        self.assertEqual(call_args["project"], self.project_uuid)
        self.assertEqual(call_args["contact_urn"], self.contact_urn)
        self.assertIn("metadata", call_args)
        self.assertIn("agent_collaboration", call_args["metadata"])
        self.assertEqual(call_args["metadata"]["agent_collaboration"]["resposta"], "5")

    def test_custom_event_data_with_invalid_json_text(self):
        """Test custom_event_data method with invalid JSON in text field"""
        custom_trace = CustomEventTraceFactory()

        # Modify the trace to have invalid JSON
        custom_trace["trace"]["orchestrationTrace"]["observation"]["actionGroupInvocationOutput"]["text"] = "invalid json"

        # Call the method
        self.adapter.custom_event_data(
            inline_trace=custom_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn
        )

        # Verify the mock was not called due to JSON parsing error
        self.mock_send_data_lake_event_task.delay.assert_not_called()

    def test_custom_event_data_with_missing_text_field(self):
        """Test custom_event_data method with missing text field"""
        custom_trace = CustomEventTraceFactory()

        # Remove the text field
        del custom_trace["trace"]["orchestrationTrace"]["observation"]["actionGroupInvocationOutput"]["text"]

        # Call the method
        self.adapter.custom_event_data(
            inline_trace=custom_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn
        )

        # Verify the mock was not called
        self.mock_send_data_lake_event_task.delay.assert_not_called()

    def test_custom_event_data_with_empty_events_list(self):
        """Test custom_event_data method with empty events list"""
        custom_trace = CustomEventTraceFactory()

        # Modify the trace to have empty events list
        custom_trace["trace"]["orchestrationTrace"]["observation"]["actionGroupInvocationOutput"]["text"] = '{"events": []}'

        # Call the method
        self.adapter.custom_event_data(
            inline_trace=custom_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn
        )

        # Verify the mock was not called
        self.mock_send_data_lake_event_task.delay.assert_not_called()

    def test_custom_event_data_with_preview_mode(self):
        """Test custom_event_data method in preview mode"""
        custom_trace = CustomEventTraceFactory()

        # Call the method with preview=True
        result = self.adapter.custom_event_data(
            inline_trace=custom_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            preview=True
        )

        # Verify the mock was not called in preview mode
        self.mock_send_data_lake_event_task.delay.assert_not_called()
        self.assertIsNone(result)