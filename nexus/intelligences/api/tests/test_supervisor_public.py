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

        # Create a conversation with required fields and dates
        from datetime import datetime, timedelta, timezone

        start_dt = datetime.now(tz=timezone.utc) - timedelta(days=2)
        end_dt = datetime.now(tz=timezone.utc) - timedelta(days=1)

        self.conversation = Conversation.objects.create(
            project=self.project,
            contact_urn="whatsapp:5511999999999",
            channel_uuid=uuid.uuid4(),
            start_date=start_dt,
            end_date=end_dt,
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

    @mock.patch("nexus.intelligences.api.supervisor_public.MessageService")
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

    def test_invalid_date_format(self):
        url = reverse(
            "public-supervisor-conversations",
            kwargs={"project_uuid": str(self.project.uuid)},
        )
        response = self.client.get(f"{url}?start=invalid-date", HTTP_AUTHORIZATION=f"ApiKey {self.raw_token}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("date", response.json())

    def test_invalid_status(self):
        url = reverse(
            "public-supervisor-conversations",
            kwargs={"project_uuid": str(self.project.uuid)},
        )
        response = self.client.get(f"{url}?status=invalid-status", HTTP_AUTHORIZATION=f"ApiKey {self.raw_token}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.json())

    @mock.patch("nexus.intelligences.api.supervisor_public.MessageService")
    def test_status_summary_aggregation(self, MockMessageService):
        # Setup mock properly to avoid recursion
        instance = MockMessageService.return_value
        instance.get_messages_for_conversation.return_value = []

        # Create multiple conversations to verify aggregation
        from datetime import datetime, timedelta, timezone

        start_dt = datetime.now(tz=timezone.utc) - timedelta(days=2)
        end_dt = datetime.now(tz=timezone.utc) - timedelta(days=1)

        # Create 5 resolved conversations
        for _ in range(5):
            Conversation.objects.create(
                project=self.project,
                contact_urn="whatsapp:123",
                channel_uuid=uuid.uuid4(),
                start_date=start_dt,
                end_date=end_dt,
                resolution=0,
            )

        # Create 3 in-progress conversations
        for _ in range(3):
            Conversation.objects.create(
                project=self.project,
                contact_urn="whatsapp:123",
                channel_uuid=uuid.uuid4(),
                start_date=start_dt,
                end_date=end_dt,
                resolution=2,
            )

        url = reverse(
            "public-supervisor-conversations",
            kwargs={"project_uuid": str(self.project.uuid)},
        )

        response = self.client.get(url, HTTP_AUTHORIZATION=f"ApiKey {self.raw_token}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        status_summary = data["status_summary"]

        # We have 1 conversation from setUp (resolution=2) + 3 created above = 4
        # We created 5 conversations with resolution=0
        self.assertEqual(status_summary["0"], 5)
        self.assertEqual(status_summary["2"], 4)
