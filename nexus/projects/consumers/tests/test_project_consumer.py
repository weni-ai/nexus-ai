from unittest import mock

from django.test import SimpleTestCase
from weni.eda.messages import Message as WeniMessage

from nexus.projects.consumers.project_consumer import WeniEDAProjectConsumer, _extract_project_payload


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
        return_value={
            "event_id": "5821d080-8d0a-42c4-955f-51107faab9ee",
            "event_type": "project.created",
            "producer": "weni-engine",
            "timestamp": "2026-08-18T13:07:15Z",
            "data": {
                "uuid": "eb83a092-12ca-4095-9d37-0151381ff45a",
                "name": "test project",
                "organization_uuid": "3d7a1d1b-3d05-44d4-bee1-55c24c8e61a9",
                "user_email": "user@test.com",
                "is_template": False,
            },
        },
    )
    @mock.patch("nexus.projects.consumers.project_consumer.ProjectsUseCase")
    def test_weni_eda_project_consumer_unwraps_event_envelope(
        self, mock_usecase_cls, _
    ):
        self.consumer._message = self.weni_message
        self.consumer.consume(self.weni_message)

        mock_usecase_cls.return_value.create_project.assert_called_once_with(
            project_dto=mock.ANY,
            user_email="user@test.com",
        )
        project_dto = mock_usecase_cls.return_value.create_project.call_args.kwargs["project_dto"]
        self.assertEqual(project_dto.uuid, "eb83a092-12ca-4095-9d37-0151381ff45a")
        self.assertEqual(project_dto.name, "test project")
        self.assertEqual(self.channel.acked, [1])

    def test_extract_project_payload_unwraps_event_envelope(self):
        envelope = {
            "event_type": "project.created",
            "data": {"uuid": "p1", "name": "Test"},
        }
        self.assertEqual(_extract_project_payload(envelope), {"uuid": "p1", "name": "Test"})

    def test_extract_project_payload_keeps_flat_body(self):
        flat = {"uuid": "p1", "name": "Test", "user_email": "user@test.com"}
        self.assertEqual(_extract_project_payload(flat), flat)

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
