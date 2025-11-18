from django.test import TestCase

from inline_agents.backends.bedrock.adapter import BedrockDataLakeEventAdapter, BedrockTeamAdapter
from inline_agents.backends.bedrock.tests.traces_factory import (
    ActionGroupTraceFactory,
    AgentCollaborationTraceFactory,
    CSATEventTraceFactory,
    CustomEventTraceFactory,
    NPSEventTraceFactory,
)
from inline_agents.data_lake import MockDataLakeEventService
from nexus.usecases.intelligences.tests.intelligence_factory import ConversationFactory


class TestBedrockDataLakeEventAdapter(TestCase):
    def setUp(self):
        self.adapter = BedrockDataLakeEventAdapter()
        self.mock_service = MockDataLakeEventService()
        self.adapter._event_service = self.mock_service
        # Create conversation with null csat and nps for testing
        self.conversation = ConversationFactory(csat=None, nps=None)
        self.project_uuid = str(self.conversation.project.uuid)
        self.contact_urn = self.conversation.contact_urn
        self.channel_uuid = self.conversation.channel_uuid

    def test_to_data_lake_event_with_action_group(self):
        action_group_trace = ActionGroupTraceFactory()

        event_data = self.adapter.to_data_lake_event(
            inline_trace=action_group_trace, project_uuid=self.project_uuid, contact_urn=self.contact_urn
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
            inline_trace=agent_trace, project_uuid=self.project_uuid, contact_urn=self.contact_urn
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
            "parameters": [{"name": "test_param", "type": "string", "value": "test_value"}],
        }

        metadata = self.adapter.metadata_action_group(action_group_input)

        self.assertEqual(metadata["tool_name"], "test_action_group")
        self.assertEqual(metadata["function_name"], "test_function")
        self.assertEqual(metadata["parameters"], action_group_input["parameters"])

    def test_metadata_agent_collaboration(self):
        agent_collaboration_input = {
            "agentCollaboratorName": "test_agent",
            "input": {"text": "test input text", "type": "TEXT"},
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
            channel_uuid=self.channel_uuid,
        )

        self.assertEqual(len(self.mock_service.sent_events), 1)

        event = self.mock_service.sent_events[0]

        # Verify the event data structure
        self.assertEqual(event["event_name"], "weni_nexus_data")
        self.assertEqual(event["key"], "csat")
        self.assertEqual(event["value_type"], "string")
        self.assertEqual(event["value"], "protocol_agent_csat")
        self.assertEqual(event["project"], self.project_uuid)
        self.assertEqual(event["contact_urn"], self.contact_urn)
        self.assertIn("metadata", event)
        self.assertIn("agent_collaboration", event["metadata"])
        self.assertEqual(event["metadata"]["agent_collaboration"]["resposta"], "5")

    def test_custom_event_data_with_invalid_json_text(self):
        """Test custom_event_data method with invalid JSON in text field"""
        custom_trace = CustomEventTraceFactory()

        custom_trace["trace"]["orchestrationTrace"]["observation"]["actionGroupInvocationOutput"]["text"] = (
            "invalid json"
        )

        self.adapter.custom_event_data(
            inline_trace=custom_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            channel_uuid=self.channel_uuid,
        )

        self.assertEqual(len(self.mock_service.sent_events), 0)

    def test_custom_event_data_with_missing_text_field(self):
        """Test custom_event_data method with missing text field"""
        custom_trace = CustomEventTraceFactory()

        del custom_trace["trace"]["orchestrationTrace"]["observation"]["actionGroupInvocationOutput"]["text"]

        self.adapter.custom_event_data(
            inline_trace=custom_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            channel_uuid=self.channel_uuid,
        )

        self.assertEqual(len(self.mock_service.sent_events), 0)

    def test_custom_event_data_with_empty_events_list(self):
        """Test custom_event_data method with empty events list"""
        custom_trace = CustomEventTraceFactory()

        custom_trace["trace"]["orchestrationTrace"]["observation"]["actionGroupInvocationOutput"]["text"] = (
            '{"events": []}'
        )

        self.adapter.custom_event_data(
            inline_trace=custom_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            channel_uuid=self.channel_uuid,
        )

        self.assertEqual(len(self.mock_service.sent_events), 0)

    def test_custom_event_data_with_preview_mode(self):
        """Test custom_event_data method in preview mode"""
        custom_trace = CustomEventTraceFactory()

        result = self.adapter.custom_event_data(
            inline_trace=custom_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            channel_uuid=self.channel_uuid,
            preview=True,
        )

        self.assertEqual(len(self.mock_service.sent_events), 0)
        self.assertIsNone(result)

    def test_custom_event_data_with_csat_event_updates_conversation(self):
        """Test that CSAT event properly updates the Conversation model"""
        csat_trace = CSATEventTraceFactory(csat_value="5")

        self.assertIsNone(self.conversation.csat)

        self.adapter.custom_event_data(
            inline_trace=csat_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            channel_uuid=self.channel_uuid,
        )

        self.conversation.refresh_from_db()

        self.assertEqual(self.conversation.csat, "5")

        self.assertEqual(len(self.mock_service.sent_events), 1)
        event = self.mock_service.sent_events[0]
        self.assertEqual(event["key"], "weni_csat")
        self.assertEqual(event["value"], "5")

    def test_custom_event_data_with_nps_event_updates_conversation(self):
        """Test that NPS event properly updates the Conversation model"""
        nps_trace = NPSEventTraceFactory(nps_value=8)

        self.assertIsNone(self.conversation.nps)

        self.adapter.custom_event_data(
            inline_trace=nps_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            channel_uuid=self.channel_uuid,
        )

        self.conversation.refresh_from_db()

        self.assertEqual(self.conversation.nps, 8)

        self.assertEqual(len(self.mock_service.sent_events), 1)
        event = self.mock_service.sent_events[0]
        self.assertEqual(event["key"], "weni_nps")
        self.assertEqual(event["value"], 8)

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
                                "totalTimeMs": 1000,
                            },
                            "text": (
                                '{"events": [{"event_name": "weni_nexus_data", "key": "weni_csat", '
                                '"value_type": "string", "value": "4", "metadata": {}}, '
                                '{"event_name": "weni_nexus_data", "key": "weni_nps", "value_type": '
                                '"string", "value": 7, "metadata": {}}]}'
                            ),
                        },
                        "traceId": "test-trace",
                        "type": "ACTION_GROUP",
                    }
                }
            },
        }

        self.assertIsNone(conversation.csat)
        self.assertIsNone(conversation.nps)

        self.adapter.custom_event_data(
            inline_trace=combined_trace,
            project_uuid=str(conversation.project.uuid),
            contact_urn=conversation.contact_urn,
            channel_uuid=conversation.channel_uuid,
        )

        conversation.refresh_from_db()

        self.assertEqual(conversation.csat, "4")
        self.assertEqual(conversation.nps, 7)

        self.assertEqual(len(self.mock_service.sent_events), 2)

        csat_events = self.mock_service.get_events_by_key("weni_csat")
        nps_events = self.mock_service.get_events_by_key("weni_nps")

        self.assertEqual(len(csat_events), 1)
        self.assertEqual(csat_events[0]["value"], "4")

        self.assertEqual(len(nps_events), 1)
        self.assertEqual(nps_events[0]["value"], 7)

    def test_custom_event_data_with_csat_event_in_preview_mode_does_not_update_conversation(self):
        """Test that CSAT event in preview mode does not update the Conversation model"""
        csat_trace = CSATEventTraceFactory(csat_value="3")

        self.assertIsNone(self.conversation.csat)

        result = self.adapter.custom_event_data(
            inline_trace=csat_trace,
            project_uuid=self.project_uuid,
            contact_urn=self.contact_urn,
            channel_uuid=self.channel_uuid,
            preview=True,
        )

        self.conversation.refresh_from_db()

        self.assertIsNone(self.conversation.csat)

        self.assertEqual(len(self.mock_service.sent_events), 0)
        self.assertIsNone(result)


class TestBedrockTeamAdapter(TestCase):
    def setUp(self):
        self.conversation = ConversationFactory()
        self.project_uuid = str(self.conversation.project.uuid)
        self.contact_urn = self.conversation.contact_urn

        self.adapter = BedrockTeamAdapter()

    def test_get_session_id_with_short_session_id(self):
        """Test that session ID is not truncated if it's not too long"""
        session_id = self.adapter._get_session_id(self.contact_urn, self.project_uuid)
        self.assertLessEqual(len(session_id), 100)
        # Should contain the full project_uuid and contact_urn
        self.assertIn(self.project_uuid, session_id)
        self.assertIn(self.contact_urn, session_id)

    def test_get_session_id_with_long_session_id_normal_project(self):
        """Test that session ID is truncated for normal projects when too long"""
        # Create a very long contact_urn that will exceed 100 characters
        long_contact_urn = (
            "whatsapp:+5511999999999@c.us.very.long.contact.identifier.that.exceeds.limits.by.a.lot."
            "and.makes.the.session.id.too.long"
        )
        session_id = self.adapter._get_session_id(long_contact_urn, self.project_uuid)
        # Should be exactly 100 characters for normal projects
        self.assertEqual(len(session_id), 100)
        self.assertTrue(session_id.startswith(f"project-{self.project_uuid}-session-"))

    def test_get_session_id_with_long_session_id_special_project(self):
        """Test that session ID preserves full project_uuid for special projects when too long"""
        from django.conf import settings

        # Mock settings to include our project as special
        original_setting = getattr(settings, "PROJECTS_WITH_SPECIAL_SESSION_ID", [])
        settings.PROJECTS_WITH_SPECIAL_SESSION_ID = [self.project_uuid]

        try:
            # Create a very long contact_urn that will exceed 100 characters
            long_contact_urn = "whatsapp:+5511999999999@c.us.very.long.contact.identifier.that.exceeds.limits.by.a.lot.and.makes.the.session.id.too.long"

            session_id = self.adapter._get_session_id(long_contact_urn, self.project_uuid)

            self.assertEqual(len(session_id), 100)
            self.assertIn(self.project_uuid, session_id)
            self.assertTrue(session_id.endswith("session.id.too.long"))
            self.assertIn("session-", session_id)

        finally:
            # Restore original setting
            settings.PROJECTS_WITH_SPECIAL_SESSION_ID = original_setting

    def test_get_session_id_sanitization(self):
        """Test that special characters in contact_urn are properly sanitized"""
        contact_urn_with_special_chars = "whatsapp:+55(11)99999-9999@c.us"

        session_id = self.adapter._get_session_id(contact_urn_with_special_chars, self.project_uuid)
        # Should contain the sanitized contact_urn
        self.assertIn("whatsapp:_43", session_id)  # + becomes _43
        self.assertIn("_40", session_id)  # ( becomes _40
        self.assertIn("_41", session_id)  # ) becomes _41
