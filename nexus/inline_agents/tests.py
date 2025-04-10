from django.test import TestCase

from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.inline_agents.models import Agent
from nexus.usecases.inline_agents.assign import AssignAgentsUsecase


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
            created_by=self.user,
        )
        self.agent.versions.create(
            skills=[],
            display_skills=[],
        )

    def test_assing_agent_doesnt_exist(self):
        with self.assertRaises(ValueError):
            self.usecase.assign_agent("123e4567-e89b-12d3-a456-426614174000", self.project.uuid, self.user)

    def test_assing_project_doesnt_exist(self):
        with self.assertRaises(ValueError):
            self.usecase.assign_agent(self.agent.uuid, "123e4567-e89b-12d3-a456-426614174000", self.user)

    def test_assign_agent(self):
        created, integrated_agent = self.usecase.assign_agent(self.agent.uuid, self.project.uuid, self.user)
        self.assertTrue(created)
        self.assertEqual(integrated_agent.agent, self.agent)
        self.assertEqual(integrated_agent.project, self.project)
        self.assertEqual(integrated_agent.created_by, self.user)

    def test_assign_agent_already_exists(self):
        self.usecase.assign_agent(self.agent.uuid, self.project.uuid, self.user)
        created, integrated_agent = self.usecase.assign_agent(self.agent.uuid, self.project.uuid, self.user)
        self.assertFalse(created)
        self.assertEqual(integrated_agent.agent, self.agent)

    def test_unassign_agent_doesnt_exist(self):
        with self.assertRaises(ValueError):
            self.usecase.unassign_agent("123e4567-e89b-12d3-a456-426614174000", self.project.uuid)

    def test_unassign_agent_project_doesnt_exist(self):
        with self.assertRaises(ValueError):
            self.usecase.unassign_agent(self.agent.uuid, "123e4567-e89b-12d3-a456-426614174000")

    def test_unassign_agent(self):
        self.usecase.assign_agent(self.agent.uuid, self.project.uuid, self.user)
        deleted, _ = self.usecase.unassign_agent(self.agent.uuid, self.project.uuid)
        self.assertTrue(deleted)

    def test_unassign_agent_already_unassigned(self):
        self.usecase.assign_agent(self.agent.uuid, self.project.uuid, self.user)
        self.usecase.unassign_agent(self.agent.uuid, self.project.uuid)
        deleted, integrated_agent = self.usecase.unassign_agent(self.agent.uuid, self.project.uuid)
        self.assertFalse(deleted)
        self.assertIsNone(integrated_agent)
