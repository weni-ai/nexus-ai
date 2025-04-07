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
        self.assertEqual(result["prompt_override_configuration"], self.supervisor.prompt_override_configuration)
        self.assertEqual(result["instruction"], self.supervisor.instruction)
        self.assertEqual(result["action_groups"], self.supervisor.action_groups)
        self.assertEqual(result["foundation_model"], self.supervisor.foundation_model)
        self.assertEqual(result["knowledge_bases"], self.supervisor.knowledge_bases)
