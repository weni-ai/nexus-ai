from unittest.mock import Mock, patch
from uuid import uuid4

import requests
from django.test import TestCase
from rest_framework import serializers

from nexus.usecases.projects.conversations import ConversationsUsecase


class MockConversationsRESTClient:
    def __init__(self):
        self.get_conversations = Mock()


class ConversationsUsecaseTestCase(TestCase):
    def setUp(self):
        self.mock_client = MockConversationsRESTClient()
        self.usecase = ConversationsUsecase(client=self.mock_client)
        self.project_uuid = str(uuid4())

    def test_get_conversations_success(self):
        """Test successful retrieval of conversations."""
        mock_conversations = [
            {
                "uuid": str(uuid4()),
                "contact_urn": "+558299999999",
                "contact_name": "João da Silva",
                "status": "Resolved",
                "resolution": 0,
                "start_date": "2024-01-20T10:00:00Z",
                "end_date": "2024-01-20T10:15:00Z",
                "channel_uuid": str(uuid4()),
                "has_chats_room": False,
                "csat": "Satisfied",
                "nps": 9,
                "created_at": "2024-01-20T10:00:00Z",
                "classification": {
                    "topic": "Financeiro",
                    "subtopic": "2ª via de boleto",
                    "confidence": 0.98,
                    "created_at": "2024-01-20T10:15:00Z",
                    "updated_at": "2024-01-20T10:15:00Z",
                },
            }
        ]

        self.mock_client.get_conversations.return_value = mock_conversations

        result = self.usecase.get_conversations(
            project_uuid=self.project_uuid,
            start_date="2024-01-20T10:00:00Z",
            end_date="2024-01-20T10:15:00Z",
            status=0,
            contact_urn="+558299999999",
            include_messages=True,
        )

        self.mock_client.get_conversations.assert_called_once_with(
            project_uuid=self.project_uuid,
            start_date="2024-01-20T10:00:00Z",
            end_date="2024-01-20T10:15:00Z",
            status=0,
            contact_urn="+558299999999",
            include_messages=True,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["contact_urn"], "+558299999999")

    def test_get_conversations_with_minimal_params(self):
        """Test retrieval with only required parameter."""
        mock_conversations = []
        self.mock_client.get_conversations.return_value = mock_conversations

        result = self.usecase.get_conversations(project_uuid=self.project_uuid)

        self.mock_client.get_conversations.assert_called_once_with(
            project_uuid=self.project_uuid,
            start_date=None,
            end_date=None,
            status=None,
            contact_urn=None,
            include_messages=None,
        )
        self.assertEqual(result, [])

    def test_get_conversations_raises_http_error(self):
        """Test that HTTPError is propagated."""
        http_error = requests.exceptions.HTTPError()
        http_error.response = Mock(status_code=500)
        self.mock_client.get_conversations.side_effect = http_error

        with self.assertRaises(requests.exceptions.HTTPError):
            self.usecase.get_conversations(project_uuid=self.project_uuid)

    def test_get_conversations_raises_validation_error(self):
        """Test that ValidationError is raised for invalid response."""
        invalid_conversations = [{"invalid": "data"}]
        self.mock_client.get_conversations.return_value = invalid_conversations

        with self.assertRaises(serializers.ValidationError):
            self.usecase.get_conversations(project_uuid=self.project_uuid)

    def test_extract_error_message_from_dict_response(self):
        """Test extracting error message from dict response."""
        mock_response = Mock()
        mock_response.json.return_value = {"error": "Custom error message"}
        mock_response.text = ""

        error_message, error_details = self.usecase.extract_error_message(mock_response)

        self.assertEqual(error_message, "Custom error message")
        self.assertEqual(error_details, {"error": "Custom error message"})

    def test_extract_error_message_from_dict_with_message_field(self):
        """Test extracting error message using 'message' field."""
        mock_response = Mock()
        mock_response.json.return_value = {"message": "Error message"}
        mock_response.text = ""

        error_message, error_details = self.usecase.extract_error_message(mock_response)

        self.assertEqual(error_message, "Error message")
        self.assertEqual(error_details, {"message": "Error message"})

    def test_extract_error_message_from_string_response(self):
        """Test extracting error message from string response."""
        mock_response = Mock()
        mock_response.json.return_value = "Simple error string"
        mock_response.text = ""

        error_message, error_details = self.usecase.extract_error_message(mock_response)

        self.assertEqual(error_message, "Simple error string")
        self.assertIsNone(error_details)

    def test_extract_error_message_from_text_response(self):
        """Test extracting error message from text when JSON fails."""
        mock_response = Mock()
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.text = "Plain text error"

        error_message, error_details = self.usecase.extract_error_message(mock_response)

        self.assertEqual(error_message, "Plain text error")
        self.assertIsNone(error_details)

    def test_extract_error_message_from_none_response(self):
        """Test extracting error message when response is None."""
        error_message, error_details = self.usecase.extract_error_message(None)

        self.assertIn("None", error_message)
        self.assertIsNone(error_details)

    @patch("nexus.usecases.projects.conversations.sentry_sdk")
    def test_send_to_sentry_with_exception(self, mock_sentry):
        """Test sending exception to Sentry."""
        exception = Exception("Test error")
        error_message = "Error message"
        error_details = {"key": "value"}
        status_code = 500

        self.usecase.send_to_sentry(
            project_uuid=self.project_uuid,
            status_code=status_code,
            error_message=error_message,
            error_details=error_details,
            exception=exception,
        )

        mock_sentry.set_tag.assert_any_call("project_uuid", self.project_uuid)
        mock_sentry.set_tag.assert_any_call("conversations_status_code", status_code)
        mock_sentry.set_context.assert_called_once_with(
            "conversations_error",
            {
                "project_uuid": self.project_uuid,
                "status_code": status_code,
                "error_message": error_message,
                "error_details": error_details,
            },
        )
        mock_sentry.capture_exception.assert_called_once_with(exception)

    @patch("nexus.usecases.projects.conversations.sentry_sdk")
    def test_send_to_sentry_without_exception(self, mock_sentry):
        """Test sending message to Sentry without exception."""
        error_message = "Error message"
        status_code = 400

        self.usecase.send_to_sentry(
            project_uuid=self.project_uuid,
            status_code=status_code,
            error_message=error_message,
            error_details=None,
            exception=None,
        )

        mock_sentry.set_tag.assert_any_call("project_uuid", self.project_uuid)
        mock_sentry.set_tag.assert_any_call("conversations_status_code", status_code)
        mock_sentry.set_context.assert_called_once_with(
            "conversations_error",
            {
                "project_uuid": self.project_uuid,
                "status_code": status_code,
                "error_message": error_message,
            },
        )
        mock_sentry.capture_message.assert_called_once_with(
            f"Conversations service error: {error_message}",
            level="error",
        )

    @patch("nexus.usecases.projects.conversations.sentry_sdk")
    def test_send_to_sentry_without_status_code(self, mock_sentry):
        """Test sending to Sentry without status code."""
        error_message = "Error message"

        self.usecase.send_to_sentry(
            project_uuid=self.project_uuid,
            status_code=None,
            error_message=error_message,
            error_details=None,
            exception=None,
        )

        mock_sentry.set_tag.assert_called_once_with("project_uuid", self.project_uuid)
        mock_sentry.set_context.assert_called_once_with(
            "conversations_error",
            {
                "project_uuid": self.project_uuid,
                "error_message": error_message,
            },
        )
        mock_sentry.capture_message.assert_called_once()

    def test_usecase_initialization_with_default_client(self):
        """Test that usecase initializes with default client when none provided."""
        usecase = ConversationsUsecase()
        self.assertIsNotNone(usecase.client)

    def test_usecase_initialization_with_custom_client(self):
        """Test that usecase uses provided client."""
        custom_client = MockConversationsRESTClient()
        usecase = ConversationsUsecase(client=custom_client)
        self.assertEqual(usecase.client, custom_client)
