from unittest.mock import patch

from django.forms.models import model_to_dict
from django.test import TestCase

from nexus.events import event_manager
from nexus.logs.models import RecentActivities
from nexus.usecases.intelligences.tests.intelligence_factory import (
    ContentBaseFactory,
    IntegratedIntelligenceFactory,
    IntelligenceFactory,
)


class IntelligenceCreateObserverTestCase(TestCase):
    @patch("nexus.event_domain.recent_activity.msg_handler.publish_external_recent_activity_to_amq")
    @patch("nexus.event_domain.recent_activity.create.publish_recent_activity_to_amq")
    def test_router_intelligence_does_not_publish_change_history(self, mock_publish_amq, mock_publish_external):
        intelligence = IntelligenceFactory(is_router=True)

        event_manager.notify(event="intelligence_create_activity", intelligence=intelligence)

        self.assertEqual(RecentActivities.objects.count(), 0)
        mock_publish_amq.assert_not_called()
        mock_publish_external.assert_not_called()

    @patch("nexus.event_domain.recent_activity.msg_handler.publish_external_recent_activity_to_amq")
    @patch("nexus.event_domain.recent_activity.create.publish_recent_activity_to_amq")
    def test_non_router_intelligence_publishes_change_history(self, mock_publish_amq, mock_publish_external):
        integrated = IntegratedIntelligenceFactory()
        intelligence = IntelligenceFactory(org=integrated.project.org, is_router=False)

        event_manager.notify(event="intelligence_create_activity", intelligence=intelligence)

        self.assertGreater(RecentActivities.objects.count(), 0)
        mock_publish_amq.assert_called()
        mock_publish_external.assert_called_once()


class ContentBaseAgentObserverTestCase(TestCase):
    def setUp(self):
        integrated_intelligence = IntegratedIntelligenceFactory()
        content_base = ContentBaseFactory(intelligence=integrated_intelligence.intelligence)
        self.content_base_agent = content_base.agent
        self.user = content_base.created_by

    def test_agent_update_activity(self):
        old_agent_data = model_to_dict(self.content_base_agent)
        self.content_base_agent.goal = "Test"
        self.content_base_agent.save()
        new_agent_data = model_to_dict(self.content_base_agent)

        event_manager.notify(
            event="contentbase_agent_activity",
            content_base_agent=self.content_base_agent,
            action_type="U",
            old_agent_data=old_agent_data,
            new_agent_data=new_agent_data,
            user=self.user,
        )

        recent_activity = RecentActivities.objects.last()

        self.assertEqual(recent_activity.action_type, "U")
        self.assertEqual(recent_activity.action_details, {"goal": {"new": "Test", "old": ""}})
