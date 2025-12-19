from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from nexus.agents.models import ActiveAgent, Agent, AgentSkills, AgentVersion, Team
from nexus.projects.models import ProjectAuth, ProjectAuthorizationRole
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.users.tests.user_factory import UserFactory


class DeleteAgentTestCase(TestCase):
    def setUp(self):
        """Set up test fixtures"""
        # Mock boto3 clients to avoid AWS credentials requirement
        self.mock_sts = MagicMock()
        self.mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}

        # Create mocks for all boto3 clients
        self.mock_s3 = MagicMock()
        self.mock_lambda = MagicMock()
        self.mock_iam = MagicMock()
        self.mock_bedrock_agent = MagicMock()
        self.mock_bedrock_agent_runtime = MagicMock()
        self.mock_bedrock_runtime = MagicMock()

        def mock_boto3_client(service_name, **kwargs):
            """Return appropriate mock based on service name"""
            mocks = {
                "sts": self.mock_sts,
                "s3": self.mock_s3,
                "lambda": self.mock_lambda,
                "iam": self.mock_iam,
                "bedrock-agent": self.mock_bedrock_agent,
                "bedrock-agent-runtime": self.mock_bedrock_agent_runtime,
                "bedrock-runtime": self.mock_bedrock_runtime,
            }
            return mocks.get(service_name, MagicMock())

        self.mock_boto3_patcher = patch("nexus.task_managers.file_database.bedrock.boto3.client")
        self.mock_boto3 = self.mock_boto3_patcher.start()
        self.mock_boto3.side_effect = mock_boto3_client

        # Create user
        self.user = UserFactory()

        # Create org and project
        self.project = ProjectFactory()
        self.project.agents_backend = "BedrockBackend"
        self.project.save()

        ProjectAuth.objects.create(user=self.user, project=self.project, role=ProjectAuthorizationRole.MODERATOR.value)

        # Create team
        self.team = Team.objects.create(
            external_id="supervisor-123", project=self.project, metadata={"supervisor_name": "test-supervisor"}
        )

        # Create Bedrock agent
        self.bedrock_agent = Agent.objects.create(
            external_id="bedrock-agent-123",
            slug="test-bedrock-agent",
            display_name="Test Bedrock Agent",
            model="anthropic.claude-v2",
            project=self.project,
            created_by=self.user,
            metadata={"engine": "BEDROCK"},
        )

        # Create OpenAI agent
        self.openai_agent = Agent.objects.create(
            external_id="openai-agent-456",
            slug="test-openai-agent",
            display_name="Test OpenAI Agent",
            model="gpt-4",
            project=self.project,
            created_by=self.user,
            metadata={},
        )

        # Add skill with Lambda to Bedrock agent
        self.skill = AgentSkills.objects.create(
            display_name="test-skill",
            unique_name="test-skill-bedrock-agent-123",
            agent=self.bedrock_agent,
            skill={
                "function_name": "test-skill-bedrock-agent-123",
                "function_arn": "arn:aws:lambda:us-east-1:123456789:function:test-skill",
                "runtime": "python3.12",
            },
            created_by=self.user,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_delete_nonexistent_agent(self):
        """Test deleting an agent that doesn't exist"""
        url = f"/api/project/{self.project.uuid}/agents/00000000-0000-0000-0000-000000000000"
        response = self.client.delete(url)

        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.data)

    def test_delete_agent_from_wrong_project(self):
        """Test deleting an agent from a different project"""
        other_project = ProjectFactory()
        other_agent = Agent.objects.create(
            external_id="other-agent",
            slug="other-agent",
            display_name="Other Agent",
            model="gpt-4",
            project=other_project,
            created_by=self.user,
        )

        url = f"/api/project/{self.project.uuid}/agents/{other_agent.uuid}"
        response = self.client.delete(url)

        self.assertEqual(response.status_code, 404)

    def test_delete_active_agent_blocked(self):
        """Test that deleting an active agent is blocked"""
        # Make agent active
        ActiveAgent.objects.create(agent=self.bedrock_agent, team=self.team, created_by=self.user)

        url = f"/api/project/{self.project.uuid}/agents/{self.bedrock_agent.uuid}"
        response = self.client.delete(url)

        self.assertEqual(response.status_code, 400)
        self.assertIn("Cannot delete active agent", response.data["error"])
        self.assertIn("active_teams", response.data)
        self.assertEqual(len(response.data["active_teams"]), 1)

    @patch("nexus.usecases.agents.agents.AgentUsecase.delete_agent")
    @patch("nexus.task_managers.file_database.bedrock.BedrockFileDatabase.delete_lambda_function")
    def test_delete_bedrock_agent_success(self, mock_delete_lambda, mock_delete_agent):
        """Test successful deletion of Bedrock agent with Lambda cleanup"""
        url = f"/api/project/{self.project.uuid}/agents/{self.bedrock_agent.uuid}"
        response = self.client.delete(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["backend_type"], "BEDROCK")
        self.assertIn("test-skill-bedrock-agent-123", response.data["lambdas_deleted"])

        # Verify Lambda was deleted
        mock_delete_lambda.assert_called_once_with("test-skill-bedrock-agent-123")

        # Verify Bedrock agent was deleted
        mock_delete_agent.assert_called_once_with("bedrock-agent-123")

        # Verify database record was deleted
        self.assertFalse(Agent.objects.filter(uuid=self.bedrock_agent.uuid).exists())

    @patch("nexus.usecases.agents.agents.AgentUsecase.delete_agent")
    @patch("nexus.task_managers.file_database.bedrock.BedrockFileDatabase.delete_lambda_function")
    def test_delete_bedrock_agent_lambda_failure_continues(self, mock_delete_lambda, mock_delete_agent):
        """Test that Lambda deletion failure doesn't block agent deletion"""
        mock_delete_lambda.side_effect = Exception("Lambda deletion failed")

        url = f"/api/project/{self.project.uuid}/agents/{self.bedrock_agent.uuid}"
        response = self.client.delete(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("warnings", response.data)
        self.assertTrue(len(response.data["warnings"]) > 0)

        # Agent should still be deleted from database
        self.assertFalse(Agent.objects.filter(uuid=self.bedrock_agent.uuid).exists())

    def test_delete_openai_agent_success(self):
        """Test successful deletion of OpenAI agent (no Lambda cleanup)"""
        self.project.agents_backend = "OpenAIBackend"
        self.project.save()
        url = f"/api/project/{self.project.uuid}/agents/{self.openai_agent.uuid}"
        response = self.client.delete(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["backend_type"], "OPENAI")
        self.assertEqual(len(response.data["lambdas_deleted"]), 0)

        # Verify database record was deleted
        self.assertFalse(Agent.objects.filter(uuid=self.openai_agent.uuid).exists())

    def test_backend_detection_by_metadata(self):
        """Test backend detection using metadata"""
        from nexus.usecases.agents.agents import AgentUsecase

        usecase = AgentUsecase()
        self.assertTrue(usecase.is_bedrock_agent(self.bedrock_agent))
        self.project.agents_backend = "OpenAIBackend"
        self.project.save()
        self.assertFalse(usecase.is_bedrock_agent(self.openai_agent))

    def test_backend_detection_by_lambda_presence(self):
        """Test backend detection by Lambda function presence"""
        from nexus.usecases.agents.agents import AgentUsecase

        # Agent without metadata but with Lambda
        agent_no_metadata = Agent.objects.create(
            external_id="agent-no-metadata",
            slug="agent-no-metadata",
            display_name="Agent No Metadata",
            model="anthropic.claude-v2",
            project=self.project,
            created_by=self.user,
            metadata={},
        )
        AgentSkills.objects.create(
            display_name="skill",
            unique_name="skill-agent-no-metadata",
            agent=agent_no_metadata,
            skill={"function_name": "some-lambda"},
            created_by=self.user,
        )

        usecase = AgentUsecase()
        self.assertTrue(usecase.is_bedrock_agent(agent_no_metadata))

    @patch("nexus.usecases.agents.agents.AgentUsecase.delete_agent")
    def test_cascade_deletes_related_records(self, mock_delete_agent):
        """Test that CASCADE deletes AgentSkills, AgentVersion, etc."""
        # Create version
        version = AgentVersion.objects.create(
            alias_id="v1", alias_name="v1", metadata={}, agent=self.bedrock_agent, created_by=self.user
        )

        skill_uuid = self.skill.uuid
        version_uuid = version.uuid

        url = f"/api/project/{self.project.uuid}/agents/{self.bedrock_agent.uuid}"
        response = self.client.delete(url)

        self.assertEqual(response.status_code, 200)

        # Verify CASCADE deleted related records
        self.assertFalse(AgentSkills.objects.filter(uuid=skill_uuid).exists())
        self.assertFalse(AgentVersion.objects.filter(uuid=version_uuid).exists())

    def tearDown(self):
        """Clean up after tests"""
        self.mock_boto3_patcher.stop()
