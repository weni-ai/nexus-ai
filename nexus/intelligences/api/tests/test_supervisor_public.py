import uuid
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from nexus.intelligences.models import Conversation
from nexus.projects.models import ProjectApiToken
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class TestSupervisorPublicAPI(TestCase):
    def setUp(self):
        self.project = ProjectFactory()
        self.user = self.project.created_by

        # Create a conversation with required fields
        self.conversation = Conversation.objects.create(
            project=self.project,
            contact_urn="whatsapp:5511999999999",
            channel_uuid=uuid.uuid4(),
        )

        # Create a valid API token
        token, salt, token_hash = ProjectApiToken.generate_token_pair()
        ProjectApiToken.objects.create(
            project=self.project,
            name="public-api-token",
            token_hash=token_hash,
            salt=salt,
            scope="read:supervisor_conversations",
            enabled=True,
            created_by=self.user,
        )

        self.raw_token = token
        self.client = APIClient()

    @mock.patch("router.services.message_service.MessageService")
    def test_public_supervisor_conversations_filters_and_messages(self, MockMessageService):
        # Mock message service to return messages
        instance = MockMessageService.return_value
        instance.get_messages_for_conversation.return_value = [
            {"text": "hello", "source": "user", "created_at": "2025-01-01T10:00:00"}
        ]

        url = reverse(
            "public-supervisor-conversations",
            kwargs={"project_uuid": str(self.project.uuid)},
        )
        start = self.conversation.start_date.date().isoformat()
        end = self.conversation.end_date.date().isoformat()
        full_url = f"{url}?start={start}&end={end}&page=1"

        response = self.client.get(full_url, HTTP_AUTHORIZATION=f"ApiKey {self.raw_token}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("results", data)
        results = data["results"]
        self.assertTrue(len(results) >= 1)
        item = results[0]
        self.assertIn("contact_urn", item)
        self.assertEqual(item["contact_urn"], self.conversation.contact_urn)
        self.assertIn("messages", item)
        self.assertEqual(item["messages"][0]["text"], "hello")
