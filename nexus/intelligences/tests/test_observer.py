from django.forms.models import model_to_dict
from django.test import TestCase

from nexus.events import event_manager
from nexus.logs.models import RecentActivities
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFactory, IntegratedIntelligenceFactory


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
