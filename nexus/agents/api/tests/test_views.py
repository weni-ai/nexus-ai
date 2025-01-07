from rest_framework.test import (
    APIRequestFactory,
    APITestCase,
    force_authenticate
)
from unittest.mock import patch, MagicMock, call
import json
from nexus.agents.api.views import PushAgents
from nexus.usecases.agents import AgentDTO

from nexus.usecases.projects.tests.project_factory import ProjectFactory


class MockAgentUsecase:
    def __init__(self, *args, **kwargs):
        pass

    def yaml_dict_to_dto(self, agents):
        return [
            AgentDTO(
                slug="agent_1",
                name="Agent 1",
                description="Description 1",
                instructions=["Instruction 1"],
                guardrails=["Guardrail 1"],
                skills=[
                    {
                        "name": "Skill 1",
                        "path": "temp/skill1.zip",
                        "slug": "skill_1"
                    }
                ],
                model="model_v1"
            ),
            AgentDTO(
                slug="agent_2",
                name="Agent 2",
                description="Description 2",
                instructions=["Instruction 2"],
                guardrails=["Guardrail 2"],
                skills=[
                    {
                        "name": "Skill 2",
                        "path": "temp/skill2.zip",
                        "slug": "skill_2"
                    }
                ],
                model="model_v2"
            )
        ]

    def create_agent(self, user, agent_dto, project_uuid):
        pass

    def create_skill(self, skill_file):
        pass


class PushAgentsTest(APITestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = PushAgents.as_view()
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.url = '/api/push_agents/'

    @patch('nexus.agents.api.views.AgentUsecase', new=MockAgentUsecase)
    @patch.object(MockAgentUsecase, 'create_agent', return_value=MagicMock(display_name='Agent 1', external_id='123'))
    @patch.object(MockAgentUsecase, 'create_skill')
    def test_push_agents(self, mock_create_skill, mock_create_agent):
        yaml_data = {
            "agents": {
                "agent_1": {
                    "name": "Agent 1",
                    "description": "Description 1",
                    "instructions": ["Instruction 1"],
                    "guardrails": ["Guardrail 1"],
                    "skills": [
                        {
                            "name": "Skill 1",
                            "path": "temp/skill1.zip",
                            "slug": "skill_1"
                        }
                    ],
                    "model": "model_v1"
                },
                "agent_2": {
                    "name": "Agent 2",
                    "description": "Description 2",
                    "instructions": ["Instruction 2"],
                    "guardrails": ["Guardrail 2"],
                    "skills": [
                        {
                            "name": "Skill 2",
                            "path": "temp/skill2.zip",
                            "slug": "skill_2"
                        }
                    ],
                    "model": "model_v2"
                }
            }
        }

        file_1 = MagicMock(name='skill1')
        file_2 = MagicMock(name='skill2')

        data = {
            'agents': json.dumps(yaml_data),
            'project': str(self.project.uuid),
            'skill_1': file_1,
            'skill_2': file_2
        }

        request = self.factory.post(self.url, data, format='multipart')
        force_authenticate(request, user=self.user)
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['agents']), 2)

        calls = [
            call(self.user, AgentDTO(
                slug="agent_1",
                name="Agent 1",
                description="Description 1",
                instructions=["Instruction 1"],
                guardrails=["Guardrail 1"],
                skills=[
                    {
                        "name": "Skill 1",
                        "path": "temp/skill1.zip",
                        "slug": "skill_1"
                    }
                ],
                model="model_v1"
            ), str(self.project.uuid)),
            call(self.user, AgentDTO(
                slug="agent_2",
                name="Agent 2",
                description="Description 2",
                instructions=["Instruction 2"],
                guardrails=["Guardrail 2"],
                skills=[
                    {
                        "name": "Skill 2",
                        "path": "temp/skill2.zip",
                        "slug": "skill_2"
                    }
                ],
                model="model_v2"
            ), str(self.project.uuid))
        ]
        mock_create_agent.assert_has_calls(calls, any_order=True)
        self.assertTrue(mock_create_skill.called)

        called_with_files = [call[0][0].name for call in mock_create_skill.call_args_list]
        self.assertIn('skill_1', called_with_files)
        self.assertIn('skill_2', called_with_files)

# ...existing code...