from unittest import mock

from django.test import SimpleTestCase
from weni.eda.messages import Message as WeniMessage

from nexus.projects.consumers.project_consumer import OldProjectConsumer, WeniEDAProjectConsumer


class DummyChannel:
    def __init__(self):
        self.acked = []
        self.rejected = []

    def basic_ack(self, tag):
        self.acked.append(tag)

    def basic_reject(self, tag, requeue=False):
        self.rejected.append((tag, requeue))


class DummyAmqpMessage:
    def __init__(self, body, channel=None):
        self.body = body
        self.channel = channel or DummyChannel()
        self.delivery_tag = 1


class OldProjectConsumerTests(SimpleTestCase):
    def setUp(self):
        self.message = DummyAmqpMessage(body=b"{}")
        self.consumer = OldProjectConsumer()

    @mock.patch(
        "nexus.projects.consumers.project_consumer.JSONParser.parse",
        return_value={
            "uuid": "p1",
            "name": "Test Project",
            "organization_uuid": "org-1",
            "user_email": "user@test.com",
        },
    )
    @mock.patch("nexus.projects.consumers.project_consumer.ProjectsUseCase")
    def test_old_project_consumer_triggers_creation(self, mock_usecase_cls, _):
        self.consumer.consume(self.message)

        mock_usecase_cls.return_value.create_project.assert_called_once()
        self.assertEqual(self.message.channel.acked, [1])

    @mock.patch(
        "nexus.projects.consumers.project_consumer.JSONParser.parse",
        return_value={"uuid": "p1"},
    )
    @mock.patch("nexus.projects.consumers.project_consumer.ProjectsUseCase")
    @mock.patch("nexus.projects.consumers.project_consumer.capture_exception")
    def test_old_project_consumer_rejects_on_error(
        self, mock_capture, mock_usecase_cls, _
    ):
        mock_usecase_cls.return_value.create_project.side_effect = RuntimeError("boom")

        self.consumer.consume(self.message)

        mock_capture.assert_called_once()
        self.assertEqual(self.message.channel.rejected, [(1, False)])


class WeniEDAProjectConsumerTests(SimpleTestCase):
    def setUp(self):
        self.channel = DummyChannel()
        self.amqp_message = DummyAmqpMessage(body=b"{}", channel=self.channel)
        self.weni_message = WeniMessage(
            body=self.amqp_message.body,
            delivery_tag=self.amqp_message.delivery_tag,
            channel=self.channel,
        )
        self.consumer = WeniEDAProjectConsumer()

    @mock.patch(
        "nexus.projects.consumers.project_consumer.JSONParser.parse",
        return_value={
            "uuid": "p1",
            "name": "Test Project",
            "organization_uuid": "org-1",
            "user_email": "user@test.com",
        },
    )
    @mock.patch("nexus.projects.consumers.project_consumer.ProjectsUseCase")
    def test_weni_eda_project_consumer_triggers_creation_and_acks(
        self, mock_usecase_cls, _
    ):
        self.consumer._message = self.weni_message
        self.consumer.consume(self.weni_message)

        mock_usecase_cls.return_value.create_project.assert_called_once()
        self.assertEqual(self.channel.acked, [1])

    @mock.patch(
        "nexus.projects.consumers.project_consumer.JSONParser.parse",
        return_value={"uuid": "p1"},
    )
    @mock.patch("nexus.projects.consumers.project_consumer.ProjectsUseCase")
    @mock.patch("nexus.projects.consumers.project_consumer.capture_exception")
    def test_weni_eda_project_consumer_rejects_on_error_via_handle(
        self, mock_capture, mock_usecase_cls, _
    ):
        mock_usecase_cls.return_value.create_project.side_effect = RuntimeError("boom")

        self.consumer.handle(self.amqp_message)

        mock_capture.assert_called_once()
        self.assertEqual(self.channel.rejected, [(1, False)])
