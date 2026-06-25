from unittest import mock

from django.test import SimpleTestCase

from nexus.projects.consumers.project_consumer import OldProjectConsumer, WeniEDAProjectConsumer


class DummyChannel:
    def __init__(self):
        self.acked = []
        self.rejected = []

    def basic_ack(self, tag):
        self.acked.append(tag)

    def basic_reject(self, tag, requeue=False):
        self.rejected.append((tag, requeue))


class DummyMessage:
    def __init__(self, body):
        self.body = body
        self.channel = DummyChannel()
        self.delivery_tag = 1


class OldProjectConsumerTests(SimpleTestCase):
    def setUp(self):
        self.message = DummyMessage(body=b"{}")
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
        self.message = DummyMessage(body=b"{}")
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
        self.consumer._message = self.message
        self.consumer.consume(self.message)

        mock_usecase_cls.return_value.create_project.assert_called_once()
        self.assertEqual(self.message.channel.acked, [1])

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

        self.consumer.handle(self.message)

        mock_capture.assert_called_once()
        self.assertEqual(self.message.channel.rejected, [(1, False)])
