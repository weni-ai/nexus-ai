from unittest.mock import Mock, patch

from django.test import TestCase

from inline_agents.backends.bedrock.adapter import BedrockTeamAdapter
from inline_agents.backends.bedrock.backend import BedrockBackend
from inline_agents.backends.tests.inline_factories import SupervisorFactory, VersionFactory


class TestBedrockAdapter(TestCase):
    def setUp(self):
        supervisor = SupervisorFactory()
        version = VersionFactory()
        agent = version.agent
        self.project = agent.project
        self.contact_urn = "whatsapp:1200000000"
        self.supervisor_dict = {
            "prompt_override_configuration": supervisor.prompt_override_configuration,
            "instruction": supervisor.instruction,
            "action_groups": supervisor.action_groups,
            "foundation_model": supervisor.foundation_model,
            "agent_collaboration": "DISABLED",
            "knowledge_bases": supervisor.knowledge_bases,
        }

        self.agents_dict = [
            {
                "agentName": agent.name,
                "instruction": agent.instruction,
                "actionGroups": version.skills,
                "foundationModel": agent.foundation_model,
                "agentCollaboration": "DISABLED",
                "collaborator_configurations": [
                    {
                        "agentAliasArn": "string",
                        "collaboratorInstruction": "string",
                        "collaboratorName": "string",
                        "relayConversationHistory": "DISABLED",
                    },
                ],
            },
        ]
        self.team_adapter = BedrockTeamAdapter()

    @patch("nexus.usecases.intelligences.get_by_uuid.get_default_content_base_by_project")
    def test_to_external(self, mock_get_content_base):
        # Mock the content base and agent
        mock_content_base = Mock()
        mock_agent = Mock()
        mock_agent.name = "Test Agent"
        mock_agent.role = "Test Role"
        mock_agent.goal = "Test Goal"
        mock_agent.personality = "Test Personality"
        mock_content_base.agent = mock_agent
        mock_content_base.instructions.all.return_value.values_list.return_value = []
        mock_get_content_base.return_value = mock_content_base

        external_team = self.team_adapter.to_external(
            self.supervisor_dict, self.agents_dict, "Hello, how are you?", self.contact_urn, self.project.uuid
        )
        import logging

        logging.getLogger(__name__).debug("External team in test", extra={"keys": list(external_team.keys())})

    def test_handle_rationale_in_response(self):
        rationale_text = "This is a rationale text"
        full_response = "This is a rationale text This is a full response"
        expected_result = "This is a full response"

        backend = BedrockBackend()

        result = backend._handle_rationale_in_response(
            rationale_texts=[rationale_text],
            full_response=full_response,
        )

        self.assertEqual(result, expected_result)
