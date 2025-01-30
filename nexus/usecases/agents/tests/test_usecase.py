from unittest.mock import Mock
from django.test import TestCase

from nexus.usecases.agents.tests.agents_factory import AgentSkillsFactory
from nexus.usecases.agents.agents import AgentUsecase
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase


class FlowsClientMock:
    def __init__(self, *args, **kwargs):
        self.list_project_contact_fields = Mock(return_value={
            'results': [
                {
                    'key': 'existing_field',
                    'label': 'Existing Field',
                    'value_type': 'text',
                    'pinned': False
                }
            ]
        })
        self.create_project_contact_field = Mock(return_value=True)


class BedrockFileDatabaseMock(BedrockFileDatabase):
    def __init__(self, *args, **kwargs):
        pass


class TestAgentsUsecase(TestCase):
    def setUp(self):
        self.flows_client = FlowsClientMock()
        self.usecase = AgentUsecase(
            external_agent_client=BedrockFileDatabaseMock,
            flows_client=lambda: self.flows_client
        )

    def test_contact_field_handler(self):
        skill_object = AgentSkillsFactory()
        self.usecase.contact_field_handler(skill_object)

        self.flows_client.list_project_contact_fields.assert_called_once_with(
            str(skill_object.agent.project.uuid)
        )

        self.flows_client.create_project_contact_field.assert_called_once_with(
            project_uuid=str(skill_object.agent.project.uuid),
            key='event',
            value_type='string'
        )
