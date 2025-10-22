from django.test import TestCase
from unittest.mock import patch, MagicMock

from nexus.logs.models import RecentActivities

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

    @patch('nexus.intelligences.api.serializers.event_manager')
    def test_update_agent(self, mock_event_manager):
        # Mock the event_manager to avoid circular import issues
        mock_event_manager.notify = MagicMock()
        
        # Import the serializer here to avoid circular import during module loading
        from nexus.intelligences.api.serializers import ContentBasePersonalizationSerializer
        
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

        # Verify that event_manager.notify was called
        mock_event_manager.notify.assert_called_once()
        
        # Check the call arguments
        call_args = mock_event_manager.notify.call_args
        self.assertEqual(call_args[1]['event'], 'contentbase_agent_activity')
        self.assertEqual(call_args[1]['action_type'], 'U')
        self.assertEqual(call_args[1]['user'], self.user)
