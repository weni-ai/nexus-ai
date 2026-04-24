import uuid
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from nexus.intelligences.api.supervisor_public import SupervisorPublicConversationsViewV2
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

    def test_v2_start_before_cut_date_returns_400(self):
        url = reverse(
            "public-supervisor-conversations-v2",
            kwargs={"project_uuid": str(self.project.uuid)},
        )
        response = self.client.get(
            f"{url}?start=2026-03-26",
            HTTP_AUTHORIZATION=f"ApiKey {self.raw_token}",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()["date"],
            "It's not possible to consult data before 27/03/2026.",
        )

    def test_v2_end_before_cut_date_returns_400(self):
        url = reverse(
            "public-supervisor-conversations-v2",
            kwargs={"project_uuid": str(self.project.uuid)},
        )
        response = self.client.get(
            f"{url}?end=2026-03-26",
            HTTP_AUTHORIZATION=f"ApiKey {self.raw_token}",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()["date"],
            "It's not possible to consult data before 27/03/2026.",
        )

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

    @mock.patch.object(SupervisorPublicConversationsViewV2, "_fetch_conversation_messages")
    @mock.patch.object(SupervisorPublicConversationsViewV2, "_call_conversations_api")
    def test_v2_list_success(self, mock_call, mock_fetch_messages):
        conv_uuid = str(uuid.uuid4())
        channel_uuid = str(uuid.uuid4())
        mock_call.return_value = {
            "results": [
                {
                    "uuid": conv_uuid,
                    "start_date": "2026-04-01T12:00:00Z",
                    "created_at": "2026-04-01T12:00:00Z",
                    "end_date": None,
                    "status": "Resolved",
                    "resolution": "0",
                    "channel_uuid": channel_uuid,
                    "contact_urn": "whatsapp:5511999999999",
                    "classification": {},
                }
            ],
            "next": None,
            "previous": None,
            "total_count": 1,
            "status_summary": {"0": 1, "1": 0, "2": 0, "3": 0, "4": 0},
        }
        mock_fetch_messages.return_value = [
            {"text": "hello", "source": "user", "created_at": "2026-04-01T12:00:01Z"},
        ]

        url = reverse(
            "public-supervisor-conversations-v2",
            kwargs={"project_uuid": str(self.project.uuid)},
        )
        response = self.client.get(url, HTTP_AUTHORIZATION=f"ApiKey {self.raw_token}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["conversation_uuid"], conv_uuid)
        self.assertEqual(data["results"][0]["contact_urn"], "whatsapp:5511999999999")
        self.assertEqual(data["results"][0]["messages"][0]["text"], "hello")
        self.assertEqual(data["status_summary"]["0"], 1)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 50)
        self.assertEqual(data["total_pages"], 1)
        self.assertIn("next", data)
        self.assertIn("previous", data)

        mock_call.assert_called_once()
        call_kw = mock_call.call_args
        self.assertEqual(str(call_kw[0][0]), str(self.project.uuid))
        self.assertEqual(call_kw[0][1]["start_date"], "2026-03-27")
        mock_fetch_messages.assert_called_once()

    @mock.patch.object(SupervisorPublicConversationsViewV2, "_fetch_conversation_messages")
    @mock.patch.object(SupervisorPublicConversationsViewV2, "_call_conversations_api")
    def test_v2_count_and_total_pages_from_upstream_total_count(self, mock_call, mock_fetch_messages):
        mock_fetch_messages.return_value = []
        mock_call.return_value = {
            "results": [],
            "next": "http://conv.example/api/v1/projects/x/conversations/?cursor=abc",
            "previous": None,
            "total_count": 250,
            "status_summary": {"0": 250, "1": 0, "2": 0, "3": 0, "4": 0},
        }
        url = reverse(
            "public-supervisor-conversations-v2",
            kwargs={"project_uuid": str(self.project.uuid)},
        )
        response = self.client.get(f"{url}?page_size=100", HTTP_AUTHORIZATION=f"ApiKey {self.raw_token}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["count"], 250)
        self.assertEqual(data["total_pages"], 3)
        self.assertEqual(data["status_summary"]["0"], 250)
        self.assertEqual(data["page"], 1)

    @mock.patch.object(SupervisorPublicConversationsViewV2, "_fetch_conversation_messages")
    @mock.patch.object(SupervisorPublicConversationsViewV2, "_call_conversations_api")
    def test_v2_page_query_echoed_like_v1(self, mock_call, mock_fetch_messages):
        mock_fetch_messages.return_value = []
        mock_call.return_value = {
            "results": [],
            "next": None,
            "previous": None,
            "total_count": 0,
            "status_summary": {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0},
        }
        url = reverse(
            "public-supervisor-conversations-v2",
            kwargs={"project_uuid": str(self.project.uuid)},
        )
        response = self.client.get(f"{url}?page=3", HTTP_AUTHORIZATION=f"ApiKey {self.raw_token}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["page"], 3)

    @mock.patch.object(SupervisorPublicConversationsViewV2, "_fetch_conversation_messages")
    @mock.patch.object(SupervisorPublicConversationsViewV2, "_call_conversations_api")
    def test_v2_status_summary_maps_unknown_resolution_to_unclassified(self, mock_call, mock_fetch_messages):
        mock_fetch_messages.return_value = []
        u1, u2, u3 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        mock_call.return_value = {
            "results": [
                {
                    "uuid": u1,
                    "resolution": None,
                    "channel_uuid": None,
                    "contact_urn": "",
                    "classification": {},
                },
                {
                    "uuid": u2,
                    "resolution": "99",
                    "channel_uuid": None,
                    "contact_urn": "",
                    "classification": {},
                },
                {
                    "uuid": u3,
                    "resolution": "1",
                    "channel_uuid": None,
                    "contact_urn": "",
                    "classification": {},
                },
            ],
            "next": None,
            "previous": None,
        }

        url = reverse(
            "public-supervisor-conversations-v2",
            kwargs={"project_uuid": str(self.project.uuid)},
        )
        response = self.client.get(url, HTTP_AUTHORIZATION=f"ApiKey {self.raw_token}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        summary = response.json()["status_summary"]
        self.assertEqual(summary["3"], 2)
        self.assertEqual(summary["1"], 1)

    @mock.patch.object(SupervisorPublicConversationsViewV2, "_fetch_conversation_messages")
    @mock.patch.object(SupervisorPublicConversationsViewV2, "_call_conversations_api")
    def test_v2_include_messages_false_skips_detail_message_fetch(self, mock_call, mock_fetch_messages):
        mock_call.return_value = {
            "results": [
                {
                    "uuid": str(uuid.uuid4()),
                    "resolution": "0",
                    "channel_uuid": None,
                    "contact_urn": "",
                    "classification": {},
                },
            ],
            "next": None,
            "previous": None,
        }

        url = reverse(
            "public-supervisor-conversations-v2",
            kwargs={"project_uuid": str(self.project.uuid)},
        )
        response = self.client.get(
            f"{url}?include_messages=false",
            HTTP_AUTHORIZATION=f"ApiKey {self.raw_token}",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["results"][0]["messages"], [])
        mock_fetch_messages.assert_not_called()

    def test_v2_invalid_page_size_returns_400(self):
        url = reverse(
            "public-supervisor-conversations-v2",
            kwargs={"project_uuid": str(self.project.uuid)},
        )
        response = self.client.get(
            f"{url}?page_size=0",
            HTTP_AUTHORIZATION=f"ApiKey {self.raw_token}",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("page_size", response.json())

    def test_v2_invalid_status_returns_400(self):
        url = reverse(
            "public-supervisor-conversations-v2",
            kwargs={"project_uuid": str(self.project.uuid)},
        )
        response = self.client.get(
            f"{url}?status=not-a-status",
            HTTP_AUTHORIZATION=f"ApiKey {self.raw_token}",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.json())

    @mock.patch.object(SupervisorPublicConversationsViewV2, "_fetch_conversation_messages")
    @mock.patch.object(SupervisorPublicConversationsViewV2, "_call_conversations_api")
    def test_v2_next_pagination_url_rewritten_to_public_endpoint(self, mock_call, mock_fetch_messages):
        mock_fetch_messages.return_value = []
        mock_call.return_value = {
            "results": [],
            "next": (
                f"https://conversations.internal/api/v1/projects/{self.project.uuid}/conversations/"
                f"?cursor=opaque-token&page_size=20"
            ),
            "previous": None,
        }

        url = reverse(
            "public-supervisor-conversations-v2",
            kwargs={"project_uuid": str(self.project.uuid)},
        )
        response = self.client.get(url, HTTP_AUTHORIZATION=f"ApiKey {self.raw_token}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        next_link = response.json()["next"]
        self.assertIn("cursor=opaque-token", next_link)
        self.assertIn(f"/public/v2/{self.project.uuid}/supervisor/conversations", next_link)
