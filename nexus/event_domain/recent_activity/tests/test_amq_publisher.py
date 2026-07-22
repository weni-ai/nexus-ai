from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from nexus.event_domain.recent_activity.create import create_recent_activity
from nexus.event_domain.recent_activity.recent_activities_dto import CreateRecentActivityDTO
from nexus.event_domain.recent_activity.recent_activity_amq import (
    _payload_from_recent_activity,
    publish_recent_activity_to_amq,
)
from nexus.logs.models import RecentActivities
from nexus.usecases.intelligences.tests.intelligence_factory import IntelligenceFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class RecentActivityAmqTestCase(TestCase):
    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.intelligence = IntelligenceFactory(created_by=self.project.created_by, org=self.project.org)

    def test_payload_from_recent_activity(self):
        recent_activity = RecentActivities.objects.create(
            action_model="ContentBase",
            action_type="U",
            project=self.project,
            created_by=self.project.created_by,
            intelligence=self.intelligence,
            action_details={"name": {"old": "a", "new": "b"}},
        )

        payload = _payload_from_recent_activity(recent_activity)

        self.assertEqual(payload["uuid"], str(recent_activity.uuid))
        self.assertEqual(payload["action"], "UPDATE")
        self.assertEqual(payload["project_uuid"], str(self.project.uuid))
        self.assertEqual(payload["user"], self.project.created_by.email)

    @override_settings(
        RECENT_ACTIVITIES_AMQ_EXCHANGE="recent-activities.topic",
        RECENT_ACTIVITIES_AMQ_ROUTING_KEY="nexus",
    )
    @patch("nexus.event_domain.recent_activity.recent_activity_amq.EDAPublisher")
    def test_publish_sends_message(self, mock_publisher_cls):
        mock_publisher = MagicMock()
        mock_publisher_cls.return_value = mock_publisher

        body = {"action": "CREATE", "entity": "NEXUS"}
        publish_recent_activity_to_amq(body=body)

        mock_publisher.send_message.assert_called_once_with(
            body=body,
            exchange="recent-activities.topic",
            routing_key="nexus",
        )

    @patch("nexus.event_domain.recent_activity.create.publish_recent_activity_to_amq")
    def test_create_publishes_to_amq(self, mock_publish):
        dto = CreateRecentActivityDTO(
            action_type="C",
            project=self.project,
            created_by=self.project.created_by,
            intelligence=self.intelligence,
            action_details={},
        )

        recent_activity = create_recent_activity(instance=self.intelligence, dto=dto)

        self.assertEqual(RecentActivities.objects.count(), 1)
        mock_publish.assert_called_once_with(recent_activity=recent_activity)
