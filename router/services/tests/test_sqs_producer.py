import hashlib
import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from router.services.sqs_producer import (
    _MESSAGE_GROUP_ID_ALLOWED,
    ConversationEventsSQSProducer,
    _fifo_message_group_digest_suffix,
    _fifo_message_group_id,
)


def _expected_hashed_group_id(project: str, channel: str, urn: str) -> str:
    prefix = f"{project}:{channel}:"
    digest = _fifo_message_group_digest_suffix(project, channel, urn)
    prefix_safe = all(c in _MESSAGE_GROUP_ID_ALLOWED for c in prefix)
    if not prefix_safe:
        return digest[:128]
    max_suffix = 128 - len(prefix)
    if max_suffix < 1:
        return digest[:128]
    return prefix + digest[:max_suffix]


class FifoMessageGroupIdTests(SimpleTestCase):
    def test_short_safe_urn_unchanged(self):
        project = "10000000-0000-0000-0000-000000000001"
        channel = "00000000-0000-0000-0000-000000000001"
        urn = "whatsapp:5584996765969"
        expected = f"{project}:{channel}:{urn}"
        out = _fifo_message_group_id(project, channel, urn)
        self.assertEqual(out, expected)
        self.assertTrue(all(c in _MESSAGE_GROUP_ID_ALLOWED for c in out))

    def test_long_contact_urn_uses_deterministic_digest_suffix(self):
        project = "a" * 36
        channel = "b" * 36
        urn = "c" * 100
        prefix = f"{project}:{channel}:"
        self.assertGreater(len(prefix + urn), 128)
        out = _fifo_message_group_id(project, channel, urn)
        self.assertEqual(len(out), 128)
        self.assertEqual(out, _expected_hashed_group_id(project, channel, urn))
        self.assertTrue(out.startswith(prefix))
        self.assertTrue(all(c in _MESSAGE_GROUP_ID_ALLOWED for c in out))

    def test_invalid_chars_in_prefix_use_digest_only(self):
        """Malformed project/channel must not be prepended on the hashed path (Qodo / SQS safety)."""
        project = "00000000-0000-0000-0000-00000000 00"  # space in UUID-shaped string
        channel = "10000000-0000-0000-0000-000000000001"
        urn = "whatsapp:1"
        digest = _fifo_message_group_digest_suffix(project, channel, urn)
        out = _fifo_message_group_id(project, channel, urn)
        self.assertEqual(out, digest[:128])
        self.assertEqual(len(out), 64)
        self.assertNotIn(" ", out)
        self.assertTrue(all(c in _MESSAGE_GROUP_ID_ALLOWED for c in out))

    def test_americanas_style_long_urn_uses_digest_suffix(self):
        project = "385c8443-249e-462e-a287-f4a0dc292915"
        channel = "41d3e926-3656-4ef4-ba2c-38b2b4b01b31"
        urn = "ext:356526701290@jsmf1585--americanasquiosque.myvtex.com"
        out = _fifo_message_group_id(project, channel, urn)
        self.assertLessEqual(len(out), 128)
        self.assertEqual(out, _expected_hashed_group_id(project, channel, urn))
        self.assertTrue(all(c in _MESSAGE_GROUP_ID_ALLOWED for c in out))

    def test_display_name_style_urn_with_spaces_uses_digest_suffix(self):
        """Production incident: spaces in contact_urn are invalid for MessageGroupId."""
        project = "c6569d72-8432-49cd-bc87-a1b1c9c3b950"
        channel = "d29f4b52-cb0a-43e5-8e32-abb522a0d1ca"
        urn = "ext:Admin MIA - IEG - 1775131903230"
        out = _fifo_message_group_id(project, channel, urn)
        self.assertNotIn(" ", out)
        self.assertEqual(out, _expected_hashed_group_id(project, channel, urn))
        self.assertTrue(all(c in _MESSAGE_GROUP_ID_ALLOWED for c in out))

    def test_space_urn_and_hyphen_urn_do_not_share_group_id(self):
        """Naive replace(' ', '-') would merge these; digest keeps them distinct."""
        project = "10000000-0000-0000-0000-000000000002"
        channel = "20000000-0000-0000-0000-000000000002"
        g1 = _fifo_message_group_id(project, channel, "ext:foo bar")
        g2 = _fifo_message_group_id(project, channel, "ext:foo-bar")
        self.assertNotEqual(g1, g2)

    def test_digest_matches_full_string_hash(self):
        project = "p" * 36
        channel = "c" * 36
        urn = "ext:weird-\u03bb"  # non-ASCII → hashed path, UTF-8 stable
        expected_hex = hashlib.sha256(f"{project}:{channel}:{urn}".encode()).hexdigest()
        self.assertEqual(_fifo_message_group_digest_suffix(project, channel, urn), expected_hex)


class ConversationEventsSQSProducerTests(SimpleTestCase):
    @override_settings(
        CONVERSATION_EVENTS_SQS_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/1/q.fifo",
        CONVERSATION_EVENTS_SQS_REGION="us-east-1",
    )
    @patch("router.services.sqs_producer.boto3.client")
    def test_send_event_message_group_id_uses_digest_for_long_urn(self, mock_boto_client):
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
        self.assertTrue(all(c in _MESSAGE_GROUP_ID_ALLOWED for c in call_kw["MessageGroupId"]))
        body = json.loads(call_kw["MessageBody"])
        self.assertEqual(body, payload)
