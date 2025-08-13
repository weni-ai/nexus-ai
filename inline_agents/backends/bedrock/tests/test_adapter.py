from django.test import TestCase
from unittest.mock import Mock

from inline_agents.backends.bedrock.adapter import BedrockDataLakeEventAdapter
from inline_agents.backends.bedrock.tests.traces_factory import (
    ActionGroupTraceFactory,
    AgentCollaborationTraceFactory,
    CustomEventTraceFactory,
    CSATEventTraceFactory,
    NPSEventTraceFactory
)
from nexus.usecases.intelligences.tests.intelligence_factory import ConversationFactory


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
        # Create conversation with null csat and nps for testing
        self.conversation = ConversationFactory(csat=None, nps=None)
        self.project_uuid = str(self.conversation.project.uuid)
        self.contact_urn = self.conversation.contact_urn
        self.channel_uuid = self.conversation.channel_uuid

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

        self.adapter.custom_event_data(
            inline_trace=custom_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            channel_uuid=self.channel_uuid
        )

        self.mock_send_data_lake_event_task.delay.assert_called_once()

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

        custom_trace["trace"]["orchestrationTrace"]["observation"]["actionGroupInvocationOutput"]["text"] = "invalid json"

        self.adapter.custom_event_data(
            inline_trace=custom_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            channel_uuid=self.channel_uuid
        )

        self.mock_send_data_lake_event_task.delay.assert_not_called()

    def test_custom_event_data_with_missing_text_field(self):
        """Test custom_event_data method with missing text field"""
        custom_trace = CustomEventTraceFactory()

        del custom_trace["trace"]["orchestrationTrace"]["observation"]["actionGroupInvocationOutput"]["text"]

        self.adapter.custom_event_data(
            inline_trace=custom_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            channel_uuid=self.channel_uuid
        )

        self.mock_send_data_lake_event_task.delay.assert_not_called()

    def test_custom_event_data_with_empty_events_list(self):
        """Test custom_event_data method with empty events list"""
        custom_trace = CustomEventTraceFactory()

        custom_trace["trace"]["orchestrationTrace"]["observation"]["actionGroupInvocationOutput"]["text"] = '{"events": []}'

        self.adapter.custom_event_data(
            inline_trace=custom_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            channel_uuid=self.channel_uuid
        )

        self.mock_send_data_lake_event_task.delay.assert_not_called()

    def test_custom_event_data_with_preview_mode(self):
        """Test custom_event_data method in preview mode"""
        custom_trace = CustomEventTraceFactory()

        result = self.adapter.custom_event_data(
            inline_trace=custom_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,   
            channel_uuid=self.channel_uuid,
            preview=True
        )

        self.mock_send_data_lake_event_task.delay.assert_not_called()
        self.assertIsNone(result)

    def test_custom_event_data_with_csat_event_updates_conversation(self):
        """Test that CSAT event properly updates the Conversation model"""
        csat_trace = CSATEventTraceFactory(csat_value="5")

        self.assertIsNone(self.conversation.csat)

        self.adapter.custom_event_data(
            inline_trace=csat_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            channel_uuid=self.channel_uuid
        )

        self.conversation.refresh_from_db()

        self.assertEqual(self.conversation.csat, "5")

        self.mock_send_data_lake_event_task.delay.assert_called_once()
        call_args = self.mock_send_data_lake_event_task.delay.call_args[0][0]
        self.assertEqual(call_args["key"], "weni_csat")
        self.assertEqual(call_args["value"], "5")

    def test_custom_event_data_with_nps_event_updates_conversation(self):
        """Test that NPS event properly updates the Conversation model"""
        nps_trace = NPSEventTraceFactory(nps_value=8)

        self.assertIsNone(self.conversation.nps)

        self.adapter.custom_event_data(
            inline_trace=nps_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            channel_uuid=self.channel_uuid
        )

        self.conversation.refresh_from_db()

        self.assertEqual(self.conversation.nps, 8)

        self.mock_send_data_lake_event_task.delay.assert_called_once()
        call_args = self.mock_send_data_lake_event_task.delay.call_args[0][0]
        self.assertEqual(call_args["key"], "weni_nps")
        self.assertEqual(call_args["value"], 8)

    def test_custom_event_data_with_both_csat_and_nps_events(self):
        """Test that both CSAT and NPS events update the Conversation model correctly"""

        conversation = ConversationFactory(csat=None, nps=None)

        combined_trace = {
            "collaboratorName": "combined_agent",
            "eventTime": "2024-01-01T00:00:00Z",
            "sessionId": "test-session",
            "trace": {
                "orchestrationTrace": {
                    "observation": {
                        "actionGroupInvocationOutput": {
                            "metadata": {
                                "clientRequestId": "test-request",
                                "endTime": "2024-01-01T00:00:01Z",
                                "startTime": "2024-01-01T00:00:00Z",
                                "totalTimeMs": 1000
                            },
                            "text": '{"events": [{"event_name": "weni_nexus_data", "key": "weni_csat", "value_type": "string", "value": "4", "metadata": {}}, {"event_name": "weni_nexus_data", "key": "weni_nps", "value_type": "string", "value": 7, "metadata": {}}]}'
                        },
                        "traceId": "test-trace",
                        "type": "ACTION_GROUP"
                    }
                }
            }
        }

        self.assertIsNone(conversation.csat)
        self.assertIsNone(conversation.nps)

        self.adapter.custom_event_data(
            inline_trace=combined_trace,
            project_uuid=str(conversation.project.uuid),
            contact_urn=conversation.contact_urn,
            channel_uuid=conversation.channel_uuid
        )

        conversation.refresh_from_db()

        self.assertEqual(conversation.csat, "4")
        self.assertEqual(conversation.nps, 7)

        self.assertEqual(self.mock_send_data_lake_event_task.delay.call_count, 2)

        first_call = self.mock_send_data_lake_event_task.delay.call_args_list[0][0][0]
        self.assertEqual(first_call["key"], "weni_csat")
        self.assertEqual(first_call["value"], "4")

        second_call = self.mock_send_data_lake_event_task.delay.call_args_list[1][0][0]
        self.assertEqual(second_call["key"], "weni_nps")
        self.assertEqual(second_call["value"], 7)

    def test_custom_event_data_with_csat_event_in_preview_mode_does_not_update_conversation(self):
        """Test that CSAT event in preview mode does not update the Conversation model"""
        csat_trace = CSATEventTraceFactory(csat_value="3")

        self.assertIsNone(self.conversation.csat)

        result = self.adapter.custom_event_data(
            inline_trace=csat_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            channel_uuid=self.channel_uuid,
            preview=True
        )

        self.conversation.refresh_from_db()

        self.assertIsNone(self.conversation.csat)

        self.mock_send_data_lake_event_task.delay.assert_not_called()
        self.assertIsNone(result)
