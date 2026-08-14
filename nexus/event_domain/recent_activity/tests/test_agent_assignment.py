from unittest.mock import patch

from django.test import TestCase

from nexus.inline_agents.models import Agent
from nexus.intelligences.models import IntegratedIntelligence
from nexus.logs.models import RecentActivities
from nexus.usecases.inline_agents.assign import AssignAgentsUsecase
from nexus.usecases.intelligences.tests.intelligence_factory import IntegratedIntelligenceFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class AssignAgentsChangeHistoryTestCase(TestCase):
    def setUp(self):
        self.integrated = IntegratedIntelligenceFactory()
        self.project = self.integrated.project
        self.user = self.project.created_by
        self.agent = Agent.objects.create(
            name="Product Concierge",
            slug="product-concierge",
            collaboration_instructions="Help customers",
            project=self.project,
            instruction="Help customers",
            foundation_model="claude",
        )
        self.agent.versions.create(skills=[], display_skills=[])
        self.usecase = AssignAgentsUsecase()

    @patch("nexus.usecases.inline_agents.assign.notify_change")
    @patch("nexus.event_domain.recent_activity.create.publish_recent_activity_to_amq")
    def test_assign_publishes_create_recent_activity(self, mock_publish_amq, mock_notify_change):
        created, _ = self.usecase.assign_agent(str(self.agent.uuid), str(self.project.uuid), user=self.user)

        self.assertTrue(created)
        activity = RecentActivities.objects.get()
        self.assertEqual(activity.action_model, "Agent")
        self.assertEqual(activity.action_type, "C")
        self.assertEqual(activity.project, self.project)
        self.assertEqual(activity.created_by, self.user)
        mock_publish_amq.assert_called_once()
        kwargs = mock_publish_amq.call_args.kwargs
        self.assertEqual(kwargs["instance"], self.agent)
        mock_notify_change.assert_not_called()

    @patch("nexus.usecases.inline_agents.assign.notify_change")
    @patch("nexus.event_domain.recent_activity.create.publish_recent_activity_to_amq")
    def test_unassign_publishes_delete_recent_activity(self, mock_publish_amq, mock_notify_change):
        self.usecase.assign_agent(str(self.agent.uuid), str(self.project.uuid), user=self.user)
        mock_publish_amq.reset_mock()

        deleted, _ = self.usecase.unassign_agent(str(self.agent.uuid), str(self.project.uuid), user=self.user)

        self.assertTrue(deleted)
        self.assertEqual(RecentActivities.objects.filter(action_type="D").count(), 1)
        activity = RecentActivities.objects.get(action_type="D")
        self.assertEqual(activity.action_model, "Agent")
        mock_publish_amq.assert_called_once()
        mock_notify_change.assert_not_called()

    @patch("nexus.usecases.inline_agents.assign.notify_change")
    @patch("nexus.event_domain.recent_activity.create.publish_recent_activity_to_amq")
    def test_assign_already_active_does_not_republish(self, mock_publish_amq, mock_notify_change):
        self.usecase.assign_agent(str(self.agent.uuid), str(self.project.uuid), user=self.user)
        mock_publish_amq.reset_mock()

        created, _ = self.usecase.assign_agent(str(self.agent.uuid), str(self.project.uuid), user=self.user)

        self.assertFalse(created)
        mock_publish_amq.assert_not_called()
        mock_notify_change.assert_not_called()

    @patch("nexus.usecases.inline_agents.assign.notify_change")
    @patch("nexus.event_domain.recent_activity.create.publish_recent_activity_to_amq")
    def test_reactivate_inactive_assignment_publishes(self, mock_publish_amq, mock_notify_change):
        _, integrated = self.usecase.assign_agent(str(self.agent.uuid), str(self.project.uuid), user=self.user)
        integrated.is_active = False
        integrated.save(update_fields=["is_active"])
        mock_publish_amq.reset_mock()

        created, _ = self.usecase.assign_agent(str(self.agent.uuid), str(self.project.uuid), user=self.user)

        self.assertFalse(created)
        mock_publish_amq.assert_called_once()
        self.assertEqual(RecentActivities.objects.filter(action_type="C").count(), 2)

    @patch("nexus.event_domain.recent_activity.create.publish_recent_activity_to_amq")
    @patch("nexus.usecases.inline_agents.assign.notify_change")
    def test_assign_without_integrated_intelligence_uses_amq_only(self, mock_notify_change, mock_publish_amq):
        project = ProjectFactory(name="No II", brain_on=True)
        self.assertFalse(IntegratedIntelligence.objects.filter(project=project).exists())
        agent = Agent.objects.create(
            name="Solo Agent",
            slug="solo-agent",
            collaboration_instructions="x",
            project=project,
            instruction="x",
            foundation_model="claude",
        )
        agent.versions.create(skills=[], display_skills=[])

        created, _ = self.usecase.assign_agent(str(agent.uuid), str(project.uuid), user=project.created_by)

        self.assertTrue(created)
        self.assertEqual(RecentActivities.objects.count(), 0)
        mock_publish_amq.assert_not_called()
        mock_notify_change.assert_called_once()
        kwargs = mock_notify_change.call_args.kwargs
        self.assertEqual(kwargs["entity"], "Agent")
        self.assertEqual(kwargs["action"], "CREATE")
        self.assertEqual(kwargs["object_name"], "Solo Agent")
