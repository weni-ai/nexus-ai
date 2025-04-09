from django.test import TestCase

from inline_agents.backends.bedrock.adapter import BedrockTeamAdapter
from inline_agents.backends.tests.inline_factories import SupervisorFactory, VersionFactory


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
