from unittest.mock import MagicMock, patch

import pendulum
from django.test import TestCase, override_settings

from nexus.event_domain.recent_activity.create import create_recent_activity
from nexus.event_domain.recent_activity.publishers_dto import RecentActivitiesDTO
from nexus.event_domain.recent_activity.recent_activities_dto import CreateRecentActivityDTO
from nexus.event_domain.recent_activity.recent_activity_amq import (
    notify_change,
    publish_external_recent_activity_to_amq,
    publish_recent_activity_to_amq,
)
from nexus.logs.models import RecentActivities
from nexus.usecases.intelligences.tests.intelligence_factory import IntelligenceFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class RecentActivityAmqTestCase(TestCase):
    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.intelligence = IntelligenceFactory(created_by=self.project.created_by, org=self.project.org)

    def tearDown(self) -> None:
        from weni.eda.connection import EDAConnection

        EDAConnection.clear_connection()

    @override_settings(
        RECENT_ACTIVITIES_AMQ_EXCHANGE="change-history.topic",
        RECENT_ACTIVITIES_AMQ_ROUTING_KEY="",
    )
    @patch("nexus.event_domain.recent_activity.recent_activity_amq.EDAConnection.clear_connection")
    @patch("nexus.event_domain.recent_activity.recent_activity_amq.EDAPublisher")
    def test_notify_change_sends_change_history_envelope(self, mock_publisher_cls, mock_clear_connection):
        mock_publisher = MagicMock()
        mock_publisher_cls.return_value = mock_publisher
        date = pendulum.datetime(2026, 5, 20, 11, 15, 0, tz="UTC")

        notify_change(
            project_uuid=str(self.project.uuid),
            user_email=self.project.created_by.email,
            date=date,
            action="UPDATE",
            entity="Project",
            object_id=str(self.project.uuid),
            object_name="brain_on",
            correlation_id="req-abc-123",
        )

        mock_publisher.send_message.assert_called_once()
        mock_clear_connection.assert_called_once()
        kwargs = mock_publisher.send_message.call_args.kwargs
        self.assertEqual(kwargs["exchange"], "change-history.topic")
        self.assertEqual(kwargs["routing_key"], "")

        body = kwargs["body"]
        self.assertEqual(body["event_type"], "nexus.project.updated")
        self.assertEqual(body["producer"], "nexus-ai")
        self.assertEqual(body["timestamp"], date.to_iso8601_string())
        self.assertEqual(body["correlation_id"], "req-abc-123")
        self.assertIn("event_id", body)
        self.assertEqual(body["data"]["project_uuid"], str(self.project.uuid))
        self.assertEqual(body["data"]["user_email"], self.project.created_by.email)
        self.assertEqual(body["data"]["action"], "UPDATE")
        self.assertEqual(body["data"]["entity"], "Project")
        self.assertEqual(body["data"]["module"], "nexus")

    @patch("nexus.event_domain.recent_activity.recent_activity_amq.EDAPublisher")
    def test_notify_change_skips_when_project_uuid_missing(self, mock_publisher_cls):
        notify_change(
            project_uuid="",
            user_email=self.project.created_by.email,
            date=pendulum.now("UTC"),
            action="UPDATE",
            entity="Project",
        )
        mock_publisher_cls.assert_not_called()

    @patch("nexus.event_domain.recent_activity.recent_activity_amq.notify_change")
    def test_publish_recent_activity_maps_to_notify_change(self, mock_notify_change):
        recent_activity = RecentActivities.objects.create(
            action_model="ContentBase",
            action_type="U",
            project=self.project,
            created_by=self.project.created_by,
            intelligence=self.intelligence,
            action_details={"name": {"old": "a", "new": "b"}},
        )

        publish_recent_activity_to_amq(recent_activity=recent_activity)

        mock_notify_change.assert_called_once()
        kwargs = mock_notify_change.call_args.kwargs
        self.assertEqual(kwargs["project_uuid"], str(self.project.uuid))
        self.assertEqual(kwargs["user_email"], self.project.created_by.email)
        self.assertEqual(kwargs["action"], "UPDATE")
        self.assertEqual(kwargs["entity"], "ContentBase")
        self.assertEqual(kwargs["object_id"], str(recent_activity.uuid))

    @patch("nexus.event_domain.recent_activity.recent_activity_amq.notify_change")
    def test_publish_external_fans_out_per_project(self, mock_notify_change):
        dto = RecentActivitiesDTO(
            org=self.project.org,
            user=self.project.created_by,
            entity_name="My Intelligence",
            action="DELETE",
        )

        publish_external_recent_activity_to_amq(dto)

        self.assertEqual(mock_notify_change.call_count, self.project.org.projects.count())
        kwargs = mock_notify_change.call_args.kwargs
        self.assertEqual(kwargs["project_uuid"], str(self.project.uuid))
        self.assertEqual(kwargs["object_name"], "My Intelligence")

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
