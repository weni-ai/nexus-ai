from django.test import TestCase

from inline_agents.backends.bedrock.adapter import BedrockTeamAdapter
from inline_agents.backends.tests.inline_factories import SupervisorFactory, VersionFactory
from nexus.event_domain.recent_activity.mocks import mock_event_manager_notify
from inline_agents.backends.bedrock.backend import BedrockBackend


class TestBedrockAdapter(TestCase):
    def setUp(self):

        supervisor = SupervisorFactory()
        version = VersionFactory()
        agent = version.agent
        self.project = agent.project
        self.contact_urn = "whatsapp:1200000000"
        self.supervisor_dict = {
            "promptOverrideConfiguration": supervisor.promptOverrideConfiguration,
            "instruction": supervisor.instruction,
            "actionGroups": supervisor.actionGroups,
            "foundationModel": supervisor.foundationModel,
            "agentCollaboration": supervisor.agentCollaboration,
            "knowledgeBases": supervisor.knowledgeBases,
        }

        self.agents_dict = [
            {
                "agentName": agent.name,
                "instruction": agent.instruction,
                "actionGroups": version.skills,
                "foundationModel": agent.foundation_model,
                "agentCollaboration": "DISABLED",
                'collaborator_configurations': [
                    {
                        'agentAliasArn': 'string',
                        'collaboratorInstruction': 'string',
                        'collaboratorName': 'string',
                        'relayConversationHistory': 'DISABLED'
                    },
                ]
            },
        ]
        self.team_adapter = BedrockTeamAdapter()

    def test_to_external(self):
        external_team = self.team_adapter.to_external(
            self.supervisor_dict,
            self.agents_dict,
            "Hello, how are you?",
            self.contact_urn,
            self.project.uuid
        )
        print(external_team)

    def test_handle_rationale_in_response(self):
        rationale_text = "This is a rationale text"
        full_response = "This is a rationale text This is a full response"
        expected_result = "This is a full response"

        session_id = "123"
        project_uuid = "456"
        contact_urn = "789"
        rationale_switch = True

        backend = BedrockBackend(mock_event_manager_notify)

        result = backend._handle_rationale_in_response(
            rationale_text=rationale_text,
            full_response=full_response,
            session_id=session_id,
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            rationale_switch=rationale_switch
        )

        self.assertEqual(result, expected_result)
