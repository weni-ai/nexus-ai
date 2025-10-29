import json
from io import BytesIO
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import InMemoryUploadedFile
from django.test import TestCase
from django.utils.datastructures import MultiValueDict

from nexus.inline_agents.models import Agent, AgentCredential, IntegratedAgent
from nexus.usecases.inline_agents.assign import AssignAgentsUsecase
from nexus.usecases.inline_agents.create import CreateAgentUseCase
from nexus.usecases.inline_agents.get import GetInlineCredentialsUsecase, GetLogGroupUsecase
from nexus.usecases.inline_agents.update import UpdateAgentUseCase
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class TestAgentsUsecase(TestCase):
    def setUp(self):
        self.usecase = AssignAgentsUsecase()
        self.project = ProjectFactory(
            name="Router",
            brain_on=True,
        )
        self.user = self.project.created_by
        self.agent = Agent.objects.create(
            name="Test Agent",
            slug="test-agent",
            collaboration_instructions="Lorem Ipsum dolor sit amet",
            project=self.project,
            instruction="Lorem Ipsum dolor sit amet",
            foundation_model="claude",
        )
        self.agent.versions.create(
            skills=[],
            display_skills=[],
        )

    def test_assing_agent_doesnt_exist(self):
        with self.assertRaises(ValueError):
            self.usecase.assign_agent("123e4567-e89b-12d3-a456-426614174000", self.project.uuid)

    def test_assing_project_doesnt_exist(self):
        with self.assertRaises(ValueError):
            self.usecase.assign_agent(self.agent.uuid, "123e4567-e89b-12d3-a456-426614174000")

    def test_assign_agent(self):
        created, integrated_agent = self.usecase.assign_agent(self.agent.uuid, self.project.uuid)
        self.assertTrue(created)
        self.assertEqual(integrated_agent.agent, self.agent)
        self.assertEqual(integrated_agent.project, self.project)

    def test_assign_agent_already_exists(self):
        self.usecase.assign_agent(self.agent.uuid, self.project.uuid)
        created, integrated_agent = self.usecase.assign_agent(self.agent.uuid, self.project.uuid)
        self.assertFalse(created)
        self.assertEqual(integrated_agent.agent, self.agent)

    def test_unassign_agent_doesnt_exist(self):
        with self.assertRaises(ValueError):
            self.usecase.unassign_agent("123e4567-e89b-12d3-a456-426614174000", self.project.uuid)

    def test_unassign_agent_project_doesnt_exist(self):
        with self.assertRaises(ValueError):
            self.usecase.unassign_agent(self.agent.uuid, "123e4567-e89b-12d3-a456-426614174000")

    def test_unassign_agent(self):
        self.usecase.assign_agent(self.agent.uuid, self.project.uuid)
        deleted, _ = self.usecase.unassign_agent(self.agent.uuid, self.project.uuid)
        self.assertTrue(deleted)

    def test_unassign_agent_already_unassigned(self):
        self.usecase.assign_agent(self.agent.uuid, self.project.uuid)
        self.usecase.unassign_agent(self.agent.uuid, self.project.uuid)
        deleted, integrated_agent = self.usecase.unassign_agent(self.agent.uuid, self.project.uuid)
        self.assertFalse(deleted)
        self.assertIsNone(integrated_agent)


class MockBedrockClient:
    def __init__(self):
        self.lambda_client = Mock()
        self.lambda_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-agent"

    def create_lambda_function(self, lambda_name, lambda_role, skill_handler, zip_buffer):
        return self.lambda_arn

    def update_lambda_function(self, lambda_name, zip_buffer):
        return self.lambda_arn

    def delete_lambda_function(self, function_name):
        return


class TestPushAgents(TestCase):
    def setUp(self):
        self.usecase = AssignAgentsUsecase()
        self.project = ProjectFactory(
            name="Router",
            brain_on=True,
        )
        self.user = self.project.created_by

        agents = """{
            "utility_agent": {
                "name": "utility agent",
                "description": "This agent provides utility functions like getting addresses "
                "from CEP, weather information and city search to get IATA codes",
                "instructions": [
                    "This agent provides utility functions like getting addresses from CEP "
                    "and weather information for cities",
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

    @patch("nexus.usecases.inline_agents.tools.FlowsRESTClient")
    def test_push_agents(self, mock_flows_client):
        mock_instance = mock_flows_client.return_value
        mock_instance.list_project_contact_fields.return_value = {"results": []}
        mock_instance.create_project_contact_field.return_value = True

        agents = self.agents
        files = MultiValueDict(
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

        agent_usecase = CreateAgentUseCase(agent_backend_client=MockBedrockClient)
        update_agent_usecase = UpdateAgentUseCase(agent_backend_client=MockBedrockClient)
        for key in agents:
            print(f"[+ ------------ Creating agent {key} ------------ +]")
            agent = agent_usecase.create_agent(key, agents[key], self.project, files)
            self.assertIsInstance(agent, Agent)
            self.assertTrue(agent.inline_contact_fields.filter(key="city").exists())

            agent_qs = Agent.objects.filter(slug=key, project=self.project)
            existing_agent = agent_qs.exists()

            print("\n[+ ---------------------------------------------- +]")

            if existing_agent:
                agents[key]["credentials"]["API_KEY"]["is_confidential"] = False
                agents[key]["credentials"]["NEW_KEY"] = {
                    "label": "New Key",
                    "placeholder": "new-key-here",
                    "is_confidential": True,
                }
                del agents[key]["credentials"]["API_SECRET"]

                agents[key]["tools"].append(
                    {
                        "key": "new_tool",
                        "slug": "new-tool",
                        "name": "new_tool",
                        "source": {
                            "path": "skills/new_tool",
                            "entrypoint": "lambda_function.lambda_handler",
                            "path_test": "test_definition.yaml",
                        },
                        "description": "A new test tool",
                        "display_name": "New Tool",
                        "parameters": [
                            {
                                "newparam": {
                                    "description": "New parameter",
                                    "type": "string",
                                    "required": True,
                                    "contact_field": True,
                                }
                            }
                        ],
                    }
                )

                files[f"{key}:new_tool"] = InMemoryUploadedFile(
                    field_name=f"{key}:new_tool",
                    name=f"{key}-new-tool.zip",
                    content_type="application/zip",
                    size=1024,
                    charset=None,
                    content_type_extra=None,
                    file=BytesIO(b"mock file content"),
                )

                print(f"[+ ------------ Updating agent {key} ------------  +]")
                agent_obj = agent_qs.first()
                update_agent_usecase.update_agent(agent_obj, agents[key], self.project, files)

                self.assertFalse(
                    AgentCredential.objects.filter(project=self.project).get(key="API_KEY").is_confidential
                )
                self.assertTrue(AgentCredential.objects.filter(project=self.project, key="NEW_KEY").exists())
                self.assertFalse(AgentCredential.objects.filter(project=self.project, key="API_SECRET").exists())

                self.assertEqual(len(agent_obj.current_version.display_skills), 2)
                self.assertEqual(len(agent_obj.current_version.skills), 2)

                self.assertEqual(agent_obj.versions.count(), 2)

                print(f"[+ ------------ Updating agent {key} again ------------  +]")
                agents[key]["tools"].pop()
                del files[f"{key}:new_tool"]
                agents[key]["tools"][0]["parameters"][0]["city"]["contact_field"] = False
                update_agent_usecase.update_agent(agent_obj, agents[key], self.project, files)

                self.assertEqual(len(agent_obj.current_version.display_skills), 1)
                self.assertEqual(len(agent_obj.current_version.skills), 1)
                self.assertEqual(agent_obj.versions.count(), 3)


class TestGetInlineCredentials(TestCase):
    def setUp(self):
        self.usecase = GetInlineCredentialsUsecase()
        self.project = ProjectFactory(
            name="Router",
            brain_on=True,
        )
        self.user = self.project.created_by

        self.agent = Agent.objects.create(
            name="Test Agent",
            slug="test-agent",
            project=self.project,
        )
        self.another_agent = Agent.objects.create(
            name="Another Agent",
            slug="another-agent",
            project=self.project,
        )
        credential = AgentCredential.objects.create(
            key="API_KEY",
            label="API Key",
            placeholder="your-api-key-here",
            is_confidential=True,
            project=self.project,
        )

        credential.agents.add(self.agent)
        credential.agents.add(self.another_agent)

        IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
        )
        IntegratedAgent.objects.create(
            agent=self.another_agent,
            project=self.project,
        )

    def test_get_credentials_by_project(self):
        official_credentials, custom_credentials = self.usecase.get_credentials_by_project(self.project.uuid)
        self.assertEqual(len(official_credentials), 0)
        self.assertEqual(len(custom_credentials), 1)
        self.agent.is_official = True
        self.agent.save()
        official_credentials, custom_credentials = self.usecase.get_credentials_by_project(self.project.uuid)
        self.assertEqual(len(official_credentials), 1)
        self.assertEqual(len(custom_credentials), 0)


class MockLogGroupBedrockClient:
    def get_log_group(self, tool_name: str) -> dict:
        return {
            "tool_name": tool_name,
            "log_group_name": f"/aws/lambda/{tool_name}",
            "log_group_arn": f"arn:aws:logs:region:XXXXXXXXX:log-group:/aws/lambda/{tool_name}",
        }


class TestGetLogGroup(TestCase):
    def setUp(self):
        self.usecase = GetLogGroupUsecase(MockLogGroupBedrockClient)
        self.project = ProjectFactory()
        self.user = self.project.created_by

        self.agent = Agent.objects.create(
            name="Test Agent",
            slug="test-agent",
            project=self.project,
        )

    def test_get_log_group(self):
        tool_key = "test-tool"
        log_group = self.usecase.get_log_group(self.project.uuid, self.agent.slug, tool_key)
        print(log_group)
        self.assertEqual(log_group.get("tool_name"), f"{tool_key}-{self.agent.id}")
