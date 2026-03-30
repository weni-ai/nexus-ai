import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.db import IntegrityError
from django.test import TestCase

from nexus.event_domain.recent_activity.mocks import mock_event_manager_notify
from nexus.projects.channel_ops import (
    channel_matches_default_preview,
    create_channel_from_wwc_event,
    get_default_channel_uuid,
)
from nexus.projects.consumers.channel_wwc_consumer import ChannelWwcConsumer
from nexus.projects.models import Channel
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.projects.tests.test_agents_backend import MockExternalAgentClient


class ChannelOpsTestCase(TestCase):
    def setUp(self) -> None:
        self.project = ProjectFactory()

    def test_create_second_channel_clears_previous_default(self) -> None:
        first = uuid4()
        second = uuid4()
        create_channel_from_wwc_event(str(self.project.uuid), str(first), "WWC")
        create_channel_from_wwc_event(str(self.project.uuid), str(second), "WWC")

        self.assertFalse(Channel.objects.get(uuid=first).is_default_for_preview)
        self.assertTrue(Channel.objects.get(uuid=second).is_default_for_preview)
        self.assertEqual(get_default_channel_uuid(str(self.project.uuid)), str(second))

    def test_create_same_uuid_raises_integrity_error(self) -> None:
        ch = uuid4()
        create_channel_from_wwc_event(str(self.project.uuid), str(ch), "WWC")
        with self.assertRaises(IntegrityError):
            create_channel_from_wwc_event(str(self.project.uuid), str(ch), "WWC")

    def test_channel_matches_default_preview(self) -> None:
        ch = uuid4()
        create_channel_from_wwc_event(str(self.project.uuid), str(ch), "WWC")
        self.assertTrue(channel_matches_default_preview(str(self.project.uuid), str(ch)))
        self.assertFalse(channel_matches_default_preview(str(self.project.uuid), str(uuid4())))
        self.assertFalse(channel_matches_default_preview(str(self.project.uuid), None))

    def test_at_most_one_default_per_project(self) -> None:
        ch1 = uuid4()
        ch2 = uuid4()
        Channel.objects.create(
            uuid=ch1,
            project=self.project,
            channel_type="WWC",
            is_default_for_preview=True,
        )
        with self.assertRaises(IntegrityError):
            Channel.objects.create(
                uuid=ch2,
                project=self.project,
                channel_type="WWC",
                is_default_for_preview=True,
            )


class ChannelWwcConsumerTestCase(TestCase):
    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.consumer = ChannelWwcConsumer()

    def _message(self, payload: dict) -> MagicMock:
        msg = MagicMock()
        msg.body = json.dumps(payload).encode()
        msg.delivery_tag = 99
        ch = MagicMock()
        msg.channel = ch
        return msg

    def test_consume_creates_channel(self) -> None:
        cid = str(uuid4())
        body = {
            "action": "anything",
            "uuid": cid,
            "project_uuid": str(self.project.uuid),
            "channel_type": "WWC",
        }
        msg = self._message(body)
        self.consumer.consume(msg)
        msg.channel.basic_ack.assert_called_once_with(99)
        self.assertTrue(Channel.objects.get(uuid=cid).is_default_for_preview)

    def test_consume_unknown_project_acks(self) -> None:
        cid = str(uuid4())
        body = {
            "uuid": cid,
            "project_uuid": str(uuid4()),
            "channel_type": "WWC",
        }
        msg = self._message(body)
        self.consumer.consume(msg)
        msg.channel.basic_ack.assert_called_once_with(99)
        self.assertFalse(Channel.objects.filter(uuid=cid).exists())

    def test_consume_rejects_when_missing_fields(self) -> None:
        msg = self._message({"uuid": str(uuid4())})
        self.consumer.consume(msg)
        msg.channel.basic_reject.assert_called_once_with(99, requeue=False)

    def test_consume_duplicate_uuid_acks_and_reports_sentry(self) -> None:
        cid = str(uuid4())
        body = {
            "uuid": cid,
            "project_uuid": str(self.project.uuid),
            "channel_type": "WWC",
        }
        create_channel_from_wwc_event(str(self.project.uuid), cid, "WWC")
        msg = self._message(body)
        with patch("nexus.projects.consumers.channel_wwc_consumer.capture_exception") as cap_exc:
            self.consumer.consume(msg)
            cap_exc.assert_called_once()
        msg.channel.basic_ack.assert_called_once_with(99)
        self.assertEqual(Channel.objects.filter(uuid=cid).count(), 1)


class ProjectDetailsDefaultChannelTestCase(TestCase):
    def test_non_inline_response_includes_default_channel_uuid(self) -> None:
        project = ProjectFactory()
        project.inline_agent_switch = False
        project.save()

        usecase = ProjectsUseCase(
            event_manager_notify=mock_event_manager_notify,
            external_agent_client=MockExternalAgentClient,
        )
        result = usecase.get_agent_builder_project_details(str(project.uuid))
        self.assertIn("default_channel_uuid", result)
        self.assertIsNone(result["default_channel_uuid"])

        ch = uuid4()
        create_channel_from_wwc_event(str(project.uuid), str(ch), "WWC")
        result2 = usecase.get_agent_builder_project_details(str(project.uuid))
        self.assertEqual(result2["default_channel_uuid"], str(ch))
