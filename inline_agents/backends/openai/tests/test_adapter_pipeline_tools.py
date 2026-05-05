"""Supervisor tool wiring by pipeline version (enhanced manager path)."""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from inline_agents.backends.openai.adapter import OpenAITeamAdapter


class ToExternalEnhancedPipelineToolsTest(SimpleTestCase):
    _project_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    def _minimal_supervisor(self):
        return {
            "instruction": "Hello {{ USE_COMPONENTS }} {{ COMPONENTS_INSTRUCTIONS }}",
            "foundation_model": "gpt-4",
            "tools": [],
            "formatter_agent_configurations": {},
            "collaborator_configurations": {},
            "model_settings": {},
            "user_model_credentials": {},
            "max_tokens": {},
        }

    @patch.object(OpenAITeamAdapter, "_get_context", return_value=MagicMock())
    @patch("inline_agents.backends.openai.adapter.SupervisorEntity")
    @patch("inline_agents.backends.openai.components_tools_stream.get_supervisor_component_tools_for_streaming_merge")
    @patch.object(OpenAITeamAdapter, "build_agents", return_value=[])
    @patch.object(OpenAITeamAdapter, "_get_tools")
    @patch.object(OpenAITeamAdapter, "get_supervisor_instructions", return_value="prompt")
    def test_new_pipeline_use_components_calls_streaming_merge_factory(
        self,
        _gsi,
        mock_get_tools,
        _build_agents,
        mock_stream_tools,
        mock_supervisor_entity,
        _mock_ctx,
    ):
        lambda_tool = MagicMock()
        lambda_tool.name = "lambda_skill"
        qr_json = MagicMock()
        qr_json.name = "create_quick_replies_message"
        mock_get_tools.return_value = [lambda_tool, qr_json]

        streaming = MagicMock()
        streaming.name = "create_quick_replies_message"
        mock_stream_tools.return_value = [streaming]

        mock_agent = MagicMock()
        mock_agent.knowledge_base_bedrock.name = "kb"
        mock_supervisor_entity.return_value = mock_agent

        OpenAITeamAdapter.to_external_enhanced(
            supervisor=self._minimal_supervisor(),
            agents=[],
            content_base_uuid="cb",
            instructions=[],
            contact_urn="u",
            contact_name="n",
            project_uuid=self._project_uuid,
            channel_uuid="ch",
            contact_fields="{}",
            business_rules="",
            use_components=True,
            agent_data={},
            data_lake_event_adapter=MagicMock(),
            hooks_state=MagicMock(),
            event_manager_notify=MagicMock(),
            preview=False,
            preview_websocket=False,
            rationale_switch=False,
            language="en",
            user_email="",
            supervisor_hooks=MagicMock(),
            input_text="hi",
            auth_token="",
            session=MagicMock(),
            session_factory=MagicMock(),
            session_id="s",
            msg_external_id="",
            turn_off_rationale=False,
            manager_pipeline_version="2.7",
        )

        # Dedupe path calls `get_supervisor_component_tools_for_streaming_merge` via both
        # `streaming_merge_tool_names` and tool injection.
        self.assertGreaterEqual(mock_stream_tools.call_count, 1)

    @patch.object(OpenAITeamAdapter, "_get_context", return_value=MagicMock())
    @patch("inline_agents.backends.openai.adapter.SupervisorEntity")
    @patch("inline_agents.backends.openai.components_tools_stream.get_supervisor_component_tools_for_streaming_merge")
    @patch.object(OpenAITeamAdapter, "build_agents", return_value=[])
    @patch.object(OpenAITeamAdapter, "_get_tools")
    @patch.object(OpenAITeamAdapter, "get_supervisor_instructions", return_value="prompt")
    def test_legacy_pipeline_skips_streaming_merge_tools(
        self,
        _gsi,
        mock_get_tools,
        _build_agents,
        mock_stream_tools,
        mock_supervisor_entity,
        _mock_ctx,
    ):
        mock_get_tools.return_value = [MagicMock(name="create_catalog_message")]
        mock_agent = MagicMock()
        mock_agent.knowledge_base_bedrock.name = "kb"
        mock_supervisor_entity.return_value = mock_agent

        OpenAITeamAdapter.to_external_enhanced(
            supervisor=self._minimal_supervisor(),
            agents=[],
            content_base_uuid="cb",
            instructions=[],
            contact_urn="u",
            contact_name="n",
            project_uuid=self._project_uuid,
            channel_uuid="ch",
            contact_fields="{}",
            business_rules="",
            use_components=True,
            agent_data={},
            data_lake_event_adapter=MagicMock(),
            hooks_state=MagicMock(),
            event_manager_notify=MagicMock(),
            preview=False,
            preview_websocket=False,
            rationale_switch=False,
            language="en",
            user_email="",
            supervisor_hooks=MagicMock(),
            input_text="hi",
            auth_token="",
            session=MagicMock(),
            session_factory=MagicMock(),
            session_id="s",
            msg_external_id="",
            turn_off_rationale=False,
            manager_pipeline_version="2.6",
        )
        mock_stream_tools.assert_not_called()
