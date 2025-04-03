from django.test import TestCase

from inline_agents.backends.tests.inline_factories import SupervisorFactory
from nexus.inline_agents.backends.bedrock.repository import BedrockSupervisorRepository


class TestBedrockSupervisorRepository(TestCase):
    def setUp(self):
        self.repository = BedrockSupervisorRepository()
        self.supervisor = SupervisorFactory()

    def test_get_supervisor(self):

        result = BedrockSupervisorRepository.get_supervisor()

        # Assert
        self.assertEqual(result["promptOverrideConfiguration"], self.supervisor.promptOverrideConfiguration)
        self.assertEqual(result["instruction"], self.supervisor.instruction)
        self.assertEqual(result["actionGroups"], self.supervisor.actionGroups)
        self.assertEqual(result["foundationModel"], self.supervisor.foundationModel)
        self.assertEqual(result["agentCollaboration"], self.supervisor.agentCollaboration)
        self.assertEqual(result["knowledgeBases"], self.supervisor.knowledgeBases)

    def test_get_action_groups(self):
        result = self.repository._get_action_groups(self.supervisor)
        self.assertEqual(result, self.supervisor.actionGroups)

    def test_get_instruction(self):
        result = self.repository._get_instruction(self.supervisor)
        self.assertEqual(result, self.supervisor.instruction)

    def test_get_foundation_model(self):
        result = self.repository._get_foundation_model(self.supervisor)
        self.assertEqual(result, self.supervisor.foundationModel)

    def test_get_agent_collaboration(self):
        result = self.repository._get_agent_collaboration(self.supervisor)
        self.assertEqual(result, self.supervisor.agentCollaboration)

    def test_get_knowledge_bases(self):
        result = self.repository._get_knowledge_bases(self.supervisor)
        self.assertEqual(result, self.supervisor.knowledgeBases)

    def test_get_prompt_override_configuration(self):
        result = self.repository._get_prompt_override_configuration(self.supervisor)
        self.assertEqual(result, self.supervisor.promptOverrideConfiguration)
