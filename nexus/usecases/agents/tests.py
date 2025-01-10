from nexus.usecases.agents import AgentDTO, AgentUsecase

from django.test import TestCase


class MockDatabase:
    def prepare_agent(self, agent_id: str):
        return

    def create_supervisor(self, supervisor_name: str, supervisor_description: str, supervisor_instructions: str):
        return "supervisor_id"

    def create_agent(self, agent_name: str, agent_description: str, agent_instructions: str):
        return "agent_id"

    def create_agent_alias(self, agent_id: str, alias_name: str):
        return "agent_alias_id", "agent_alias_arn"


class TestAgentUseCase(TestCase):

    def setUp(self):
        self.usecase = AgentUsecase(external_agent_client=MockDatabase)

    def test_yaml_dict_to_dto(self):
        yaml_data = {
            "agents": {
                "teste_exemplo": {
                    "name": "Teste Exemplo",
                    "description": "Agente de exemplo da weni",
                    "instructions": ["intrução 1", "instrução 2"],
                    "guardrails": ["Não fale sobre apostas"],
                    "skills": [
                        {
                            "name": "Get Order",
                            "path": "temp/file_name.zip",
                            "slug": "get_order"
                        }
                    ],
                    "model": "model_v1"
                }
            }
        }

        expected_result = [
            AgentDTO(
                slug="teste_exemplo",
                name="Teste Exemplo",
                description="Agente de exemplo da weni",
                instructions=["intrução 1", "instrução 2"],
                guardrails=["Não fale sobre apostas"],
                skills=[
                    {
                        {
                            "name": "Get Order",
                            "path": "temp/file_name.zip",
                            "slug": "get_order"
                        }
                    }
                ],
                model="model_v1"
            )
        ]
        result = self.usecase.yaml_dict_to_dto(yaml_data)
        self.assertEqual(result, expected_result)
