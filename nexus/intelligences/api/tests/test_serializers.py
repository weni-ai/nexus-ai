from django.test import TestCase

from nexus.logs.models import RecentActivities

from nexus.intelligences.api.serializers import ContentBasePersonalizationSerializer

from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFactory, IntegratedIntelligenceFactory


class MockRequest:
    def __init__(self, user):
        self.user = user
        self.data = {}


class ContentBasePersonalizationSerializerTestCase(TestCase):
    def setUp(self) -> None:
        integrated_intelligence = IntegratedIntelligenceFactory()
        intelligence = integrated_intelligence.intelligence
        self.content_base = ContentBaseFactory(
            intelligence=intelligence,
            created_by=integrated_intelligence.created_by
        )
        self.agent = self.content_base.agent
        self.instructions = self.content_base.instructions.all()
        self.user = self.content_base.created_by

    def test_update_agent(self):
        agent_data = {
            "name": "new name",
            "role": "new role",
            "personality": "new personality",
            "goal": "new goal",
        }
        request = MockRequest(user=self.user)
        request.data.update({"instructions": []})

        serializer = ContentBasePersonalizationSerializer(
            instance=self.content_base,
            data={"agent": agent_data},
            context={"request": request},
            partial=True
        )
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.name, agent_data["name"])
        self.assertEqual(self.agent.role, agent_data["role"])
        self.assertEqual(self.agent.personality, agent_data["personality"])
        self.assertEqual(self.agent.goal, agent_data["goal"])

        recent_activity = RecentActivities.objects.last()
        self.assertEqual(recent_activity.action_type, "U")

        action_details = {
            'goal': {
                'new': 'new goal',
                'old': ''
            },
            'name': {
                'new': 'new name',
                'old': None
            },
            'role': {
                'new': 'new role',
                'old': None
            },
            'personality': {
                'new': 'new personality',
                'old': None
            }
        }
        self.assertEqual(recent_activity.action_details, action_details)
