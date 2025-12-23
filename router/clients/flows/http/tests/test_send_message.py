"""
Tests for send_message.py - specifically for Error #3 fix.

TC-05: Test that format_message_for_openai handles non-JSON responses correctly.

Error #3: ValueError: dictionary update sequence element #0 has length 1; 2 is required
This occurred when LLM returned plain text instead of JSON, and the code tried
to call body.update(string) instead of body.update(dict).
"""

import json
from unittest.mock import patch

from django.test import TestCase

from router.clients.flows.http.send_message import WhatsAppBroadcastHTTPClient


class TestFormatMessageForOpenAI(TestCase):
    """
    TC-05: Test format_message_for_openai handles non-JSON responses.

    These tests verify the fix for Error #3:
    ValueError: dictionary update sequence element #0 has length 1; 2 is required
    on body.update(msg) when msg is a string instead of dict.
    """

    def setUp(self):
        """Set up test client."""
        self.client = WhatsAppBroadcastHTTPClient(host="http://test", access_token="test-token")

    @patch("router.clients.flows.http.send_message.sentry_sdk")
    def test_format_non_json_response_returns_dict_list(self, mock_sentry):
        """TC-05a: Test that plain text response is wrapped in proper dict structure."""
        raw_text_response = "Agradeco seu feedback! Como posso ajudar?"

        result = self.client.format_message_for_openai(
            msg=raw_text_response,
            urns=["whatsapp:123"],
            project_uuid="test-uuid",
            user="test@example.com",
            full_chunks=[],
        )

        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

        first_msg = result[0]
        self.assertIsInstance(first_msg, dict, "Result should contain dicts, not strings")
        self.assertIn("msg", first_msg)
        self.assertIsInstance(first_msg["msg"], dict)
        self.assertIn("text", first_msg["msg"])
        self.assertEqual(first_msg["msg"]["text"], raw_text_response)

    @patch("router.clients.flows.http.send_message.sentry_sdk")
    def test_format_non_json_does_not_return_raw_string(self, mock_sentry):
        """TC-05b: Test that result NEVER contains raw strings."""
        plain_text_responses = [
            "Simple response",
            "Agradeco seu feedback!",
            "Hello, how can I help you today?",
        ]

        for raw_text in plain_text_responses:
            with self.subTest(raw_text=raw_text[:30]):
                result = self.client.format_message_for_openai(
                    msg=raw_text,
                    urns=["whatsapp:123"],
                    project_uuid="test-uuid",
                    user="test@example.com",
                    full_chunks=[],
                )

                for item in result:
                    self.assertNotIsInstance(
                        item, str, f"format_message_for_openai should not return strings. Got: {type(item)}"
                    )

    @patch("router.clients.flows.http.send_message.sentry_sdk")
    def test_format_valid_json_response(self, mock_sentry):
        """TC-05c: Test that valid JSON response is parsed correctly."""
        json_response = json.dumps({"msg": {"text": "Hello from JSON"}})

        result = self.client.format_message_for_openai(
            msg=json_response,
            urns=["whatsapp:123"],
            project_uuid="test-uuid",
            user="test@example.com",
            full_chunks=[],
        )

        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        first_msg = result[0]
        self.assertIsInstance(first_msg, dict)

    @patch("router.clients.flows.http.send_message.sentry_sdk")
    def test_format_json_list_response(self, mock_sentry):
        """TC-05d: Test that valid JSON list response is handled correctly."""
        json_list_response = json.dumps(
            [
                {"msg": {"text": "First message"}},
                {"msg": {"text": "Second message"}},
            ]
        )

        result = self.client.format_message_for_openai(
            msg=json_list_response,
            urns=["whatsapp:123"],
            project_uuid="test-uuid",
            user="test@example.com",
            full_chunks=[],
        )

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

    @patch("router.clients.flows.http.send_message.sentry_sdk")
    def test_format_non_json_logs_to_sentry(self, mock_sentry):
        """TC-05e: Test that non-JSON responses are logged to Sentry."""
        raw_text = "Non-JSON response"

        self.client.format_message_for_openai(
            msg=raw_text,
            urns=["whatsapp:123"],
            project_uuid="test-uuid",
            user="test@example.com",
            full_chunks=[],
        )

        mock_sentry.set_tag.assert_called()
        mock_sentry.set_context.assert_called()
        mock_sentry.capture_exception.assert_called()

    @patch("router.clients.flows.http.send_message.sentry_sdk")
    def test_format_result_can_be_used_in_update(self, mock_sentry):
        """TC-05f: Test that result can be safely used in dict.update()."""
        raw_text = "Plain text that caused the ValueError"

        result = self.client.format_message_for_openai(
            msg=raw_text,
            urns=["whatsapp:123"],
            project_uuid="test-uuid",
            user="test@example.com",
            full_chunks=[],
        )

        body = {"urns": ["whatsapp:123"], "project": "test-uuid"}

        try:
            body.update(result[0])
        except ValueError as e:
            self.fail(f"ValueError raised when using result in dict.update(): {e}")

        self.assertIn("msg", body)


class TestFormatResponseForBedrock(TestCase):
    """Test that Bedrock formatting (which already worked) is still correct."""

    def setUp(self):
        """Set up test client."""
        self.client = WhatsAppBroadcastHTTPClient(host="http://test", access_token="test-token")

    def test_bedrock_format_non_json_wraps_in_dict(self):
        """Test that Bedrock format wraps non-JSON in dict."""
        raw_text = "Plain text response"

        result = self.client.format_response_for_bedrock(
            msg=raw_text,
            urns=["whatsapp:123"],
            project_uuid="test-uuid",
            user="test@example.com",
            full_chunks=[],
        )

        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

        first_msg = result[0]
        self.assertIsInstance(first_msg, dict)
        self.assertIn("msg", first_msg)
        self.assertIn("text", first_msg["msg"])
