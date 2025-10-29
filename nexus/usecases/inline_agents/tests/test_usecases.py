import json
from io import BytesIO
from unittest.mock import patch

from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.test import TestCase
from django.utils.datastructures import MultiValueDict

from nexus.inline_agents.tests import MockBedrockClient
from nexus.usecases.inline_agents.create import CreateAgentUseCase
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class TestCreateAgentsUsecase(TestCase):
    def setUp(self):
        self.usecase = CreateAgentUseCase(agent_backend_client=MockBedrockClient)
        self.project = ProjectFactory(
            name="Router",
            brain_on=True,
        )
        self.user = self.project.created_by

        agents = """{
            "utility_agent": {
                "name": "utility agent",
                "description": "This agent provides utility functions for addresses, weather and city search",
                "instructions": [
                    "This agent provides utility functions for addresses and weather",
                    "For weather requests, inform the user if the requested date is beyond the 7-day forecast limit",
                    "For city searches, provide IATA codes and additional information about matching cities",
                    "If you don't know the answer, don't lie. Tell the user you don't know."
                ],
                "guardrails": [
                    "Don't talk about politics, religion or any other sensitive topic. Keep it neutral."
                ],
                "credentials": {
                    "API_KEY": {
                        "label": "API Key",
                        "placeholder": "your-api-key-here",
                        "is_confidential": true
                    },
                    "API_SECRET": {
                        "label": "API Secret",
                        "placeholder": "your-api-secret-here"
                    },
                    "BASE_URL": {
                        "label": "Base URL",
                        "placeholder": "https://api.example.com",
                        "is_confidential": false
                    }
                },
                "tools": [
                    {
                        "key": "get_weather",
                        "slug": "get-weather",
                        "name": "Get Weather",
                        "source": {
                            "path": "skills/get_weather",
                            "entrypoint": "lambda_function.lambda_handler",
                            "path_test": "test_definition.yaml"
                        },
                        "description": "Function to get the weather information from the city",
                        "parameters": [
                            {
                                "city": {
                                    "description": "Name of the city to get weather information",
                                    "type": "string",
                                    "required": true,
                                    "contact_field": true
                                }
                            }
                        ]
                    }
                ],
                "slug": "utility-agent"
            }
        }"""
        self.agents = json.loads(agents)
        self.files = MultiValueDict(
            {
                "utility_agent:get_weather": [
                    InMemoryUploadedFile(
                        field_name="utility_agent:get_weather",
                        name="utility-agent:get-weather.zip",
                        content_type="application/zip",
                        size=1024,
                        charset=None,
                        content_type_extra=None,
                        file=BytesIO(b"mock file content"),
                    )
                ]
            }
        )

    @patch("nexus.usecases.inline_agents.tools.FlowsRESTClient")
    def test_create_agents(self, mock_flows_client):
        mock_instance = mock_flows_client.return_value
        mock_instance.list_project_contact_fields.return_value = {"results": []}

        agents = self.agents
        for key in agents:
            agent = self.usecase.create_agent(key, agents[key], self.project, self.files)
            self.assertEqual(agent.backend_foundation_models, settings.DEFAULT_FOUNDATION_MODELS)

        mock_instance.list_project_contact_fields.assert_called()
