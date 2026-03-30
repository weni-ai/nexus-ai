import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from router.services.sqs_producer import (
    ConversationEventsSQSProducer,
    _fifo_message_group_id,
)


class FifoMessageGroupIdTests(SimpleTestCase):
    def test_short_unchanged(self):
        channel = "00000000-0000-0000-0000-000000000001"
        urn = "whatsapp:5584996765969"
        assert _fifo_message_group_id(channel, urn) == f"{channel}:{urn}"

    def test_truncates_to_128(self):
        channel = "a" * 36
        urn = "b" * 100
        raw = f"{channel}:{urn}"
        self.assertGreater(len(raw), 128)
        out = _fifo_message_group_id(channel, urn)
        self.assertEqual(len(out), 128)
        self.assertEqual(out, raw[:128])


class ConversationEventsSQSProducerTests(SimpleTestCase):
    @override_settings(
        CONVERSATION_EVENTS_SQS_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/1/q.fifo",
        CONVERSATION_EVENTS_SQS_REGION="us-east-1",
    )
    @patch("router.services.sqs_producer.boto3.client")
    def test_send_event_uses_channel_and_contact_for_message_group_id(self, mock_boto_client):
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
        expected_gid = (
            "41d3e926-3656-4ef4-ba2c-38b2b4b01b31:" "ext:356526701290@jsmf1585--americanasquiosque.myvtex.com"
        )
        self.assertEqual(call_kw["MessageGroupId"], expected_gid)
        self.assertLessEqual(len(call_kw["MessageGroupId"]), 128)
        body = json.loads(call_kw["MessageBody"])
        self.assertEqual(body, payload)
