import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from router.services.sqs_producer import (
    ConversationEventsSQSProducer,
    _fifo_message_group_id,
)


class FifoMessageGroupIdTests(SimpleTestCase):
    def test_short_unchanged(self):
        project = "10000000-0000-0000-0000-000000000001"
        channel = "00000000-0000-0000-0000-000000000001"
        urn = "whatsapp:5584996765969"
        expected = f"{project}:{channel}:{urn}"
        self.assertEqual(_fifo_message_group_id(project, channel, urn), expected)

    def test_truncates_contact_urn_only_preserves_uuids(self):
        project = "a" * 36
        channel = "b" * 36
        urn = "c" * 100
        prefix = f"{project}:{channel}:"
        self.assertGreater(len(prefix + urn), 128)
        out = _fifo_message_group_id(project, channel, urn)
        self.assertEqual(len(out), 128)
        self.assertTrue(out.startswith(prefix))
        self.assertEqual(out, prefix + urn[: 128 - len(prefix)])

    def test_americanas_style_incident_fits_128(self):
        project = "385c8443-249e-462e-a287-f4a0dc292915"
        channel = "41d3e926-3656-4ef4-ba2c-38b2b4b01b31"
        urn = "ext:356526701290@jsmf1585--americanasquiosque.myvtex.com"
        out = _fifo_message_group_id(project, channel, urn)
        self.assertLessEqual(len(out), 128)
        prefix = f"{project}:{channel}:"
        self.assertEqual(out, prefix + urn[: 128 - len(prefix)])


class ConversationEventsSQSProducerTests(SimpleTestCase):
    @override_settings(
        CONVERSATION_EVENTS_SQS_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/1/q.fifo",
        CONVERSATION_EVENTS_SQS_REGION="us-east-1",
    )
    @patch("router.services.sqs_producer.boto3.client")
    def test_send_event_message_group_id_project_channel_urn_truncated(self, mock_boto_client):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        payload = {
            "correlation_id": "corr-1",
            "event_type": "message.sent",
            "data": {
                "project_uuid": "385c8443-249e-462e-a287-f4a0dc292915",
                "contact_urn": "ext:356526701290@jsmf1585--americanasquiosque.myvtex.com",
                "channel_uuid": "41d3e926-3656-4ef4-ba2c-38b2b4b01b31",
            },
        }

        producer = ConversationEventsSQSProducer()
        producer.send_event(payload)

        mock_boto_client.assert_called_once_with("sqs", region_name="us-east-1")
        call_kw = mock_client.send_message.call_args.kwargs
        expected_gid = _fifo_message_group_id(
            payload["data"]["project_uuid"],
            payload["data"]["channel_uuid"],
            payload["data"]["contact_urn"],
        )
        self.assertEqual(call_kw["MessageGroupId"], expected_gid)
        self.assertLessEqual(len(call_kw["MessageGroupId"]), 128)
        body = json.loads(call_kw["MessageBody"])
        self.assertEqual(body, payload)
