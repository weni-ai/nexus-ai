import json
from uuid import uuid4

import pendulum
from freezegun import freeze_time

from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate, APITestCase, APIClient

from nexus.actions.models import Flow

from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.logs.tests.logs_factory import RecentActivitiesFactory, MessageLogFactory
from nexus.usecases.intelligences.tests.intelligence_factory import LLMFactory
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project
from nexus.usecases.intelligences.create import create_base_brain_structure
from nexus.usecases.users.tests.user_factory import UserFactory
from nexus.usecases.inline_agents.tests.inline_factories import InlineAgentMessageFactory

from nexus.logs.models import MessageLog, Message
from nexus.logs.api.serializers import MessageLogSerializer

from nexus.logs.api.views import (
    LogsViewset,
    RecentActivitiesViewset,
    MessageHistoryViewset,
    TagPercentageViewSet,
    InlineConversationsViewset
)


class LogSerializersTestCase(TestCase):
    def setUp(self) -> None:
        self.llm = LLMFactory()
        self.project = ProjectFactory()
        self.content_base = get_default_content_base_by_project(str(self.project.uuid))

    def test_message_log_serializer(self):
        message = Message.objects.create(
            text="Test Message",
            contact_urn="tel:123321",
        )

        log = MessageLog.objects.create(
            message=message,
            chunks=["Test 1", "Test 2", "Test 3"],
            prompt="Lorem Ipsum",
            project=self.project,
            content_base=self.content_base,
            classification="other",
            llm_model="test gpt",
            llm_response="Test mode",
            metadata={}
        )
        message_log = MessageLogSerializer(log)
        self.assertEqual(message_log.data.get("message_text"), "Test Message")


class LogsViewSetTestCase(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.content_base = get_default_content_base_by_project(str(self.project.uuid))

        with freeze_time(str(pendulum.now().subtract(months=1))):
            message = Message.objects.create(
                text="Test Message",
                contact_urn="tel:123321",
            )

            MessageLog.objects.create(
                message=message,
                chunks=["Test 1", "Test 2", "Test 3"],
                prompt="Lorem Ipsum",
                project=self.project,
                content_base=self.content_base,
                classification="other",
                llm_model="test gpt",
                llm_response="Test mode",
                metadata={}
            )

        message2 = Message.objects.create(
            text="Test Message",
            contact_urn="tel:321123",
        )
        MessageLog.objects.create(
            message=message2,
            chunks=[],
            prompt="Lorem Ipsum",
            project=self.project,
            content_base=self.content_base,
            classification="other",
            llm_model="test gpt",
            llm_response="Test mode",
            metadata={}
        )

    def test_get_personalization(self):
        request = self.factory.get(f"api/{self.project.uuid}/logs/?contact_urn=tel:123321&limit=100")

        force_authenticate(request, user=self.user)

        response = LogsViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )

        response.render()
        content = json.loads(response.content).get("results")

        self.assertEqual(response.status_code, 200)
        self.assertEquals(len(content), 1)

    def test_order_by_desc(self):
        request = self.factory.get(f"api/{self.project.uuid}/logs/?order_by=desc&limit=100")
        force_authenticate(request, user=self.user)
        response = LogsViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )

        response.render()
        content = json.loads(response.content)
        content = content.get("results")

        first = pendulum.parse(content[0].get("created_at"))
        last = pendulum.parse(content[1].get("created_at"))

        self.assertGreater(first, last)

    def test_order_by_asc(self):
        request = self.factory.get(f"api/{self.project.uuid}/logs/?order_by=asc&limit=100")
        force_authenticate(request, user=self.user)
        response = LogsViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )

        response.render()
        content = json.loads(response.content)
        content = content.get("results")

        first = pendulum.parse(content[0].get("created_at"))
        last = pendulum.parse(content[1].get("created_at"))

        self.assertGreater(last, first)

    def test_get_log(self):
        fields = [
            "message_text",
            "message_exception",
            "contact_urn",
            "chunks",
            "prompt",
            "project",
            "content_base",
            "classification",
            "llm_model",
            "llm_response",
            "created_at",
            "metadata",
        ]

        log_id = MessageLog.objects.first().id
        request = self.factory.get(f"api/{self.project.uuid}/logs/{log_id}")

        force_authenticate(request, user=self.user)
        response = LogsViewset.as_view({'get': 'retrieve'})(
            request,
            project_uuid=str(self.project.uuid),
            log_id=log_id,
        )
        response.render()

        content = json.loads(response.content)
        self.assertListEqual(fields, list(content.keys()))


class RecentActivitiesViewSetTestCase(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.recent_activity = RecentActivitiesFactory(
            project=self.project
        )

    def test_get_recent_activities(self):
        request = self.factory.get(f"api/{self.project.uuid}/activities/?page_size=100")
        force_authenticate(request, user=self.user)
        response = RecentActivitiesViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )

        response.render()
        content = json.loads(response.content).get("results")

        self.assertEqual(response.status_code, 200)
        self.assertEquals(len(content), 1)

    def test_pagination(self):
        RecentActivitiesFactory(
            project=self.project
        )
        request = self.factory.get(f"api/{self.project.uuid}/activities/?page_size=1")
        force_authenticate(request, user=self.user)
        response = RecentActivitiesViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )

        response.render()
        content = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEquals(len(content.get("results")), 1)
        self.assertIsNotNone(content.get("next"))

    def test_no_permission(self):
        request = self.factory.get(f"api/{self.project.uuid}/activities/?page_size=100")
        response = RecentActivitiesViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )

        response.render()
        self.assertEqual(response.status_code, 401)
        self.assertEquals(json.loads(response.content).get("detail"), "Authentication credentials were not provided.")

    def test_action_model_groups_filter(self):
        self.recent_activity.action_model = "Invalid"
        self.recent_activity.save()
        self.recent_activity.refresh_from_db()
        request = self.factory.get(f"api/{self.project.uuid}/activities/?page_size=100")
        force_authenticate(request, user=self.user)
        response = RecentActivitiesViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )
        response.render()
        self.assertEqual(response.status_code, 200)
        content = json.loads(response.content).get("results")
        self.assertEquals(len(content), 0)


class MessageHistoryViewsetTestCase(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.started_day = pendulum.now().subtract(months=1).to_date_string()
        self.ended_day = pendulum.now().to_date_string()

        MessageLogFactory.create_batch(10, project=self.project)

    def test_message_history_viewset(self):
        request = self.factory.get(f"/api/{self.project.uuid}/message_history/?page_size=100&started_day={self.started_day}&ended_day={self.ended_day}")
        force_authenticate(request, user=self.user)
        response = MessageHistoryViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )

        response.render()

        self.assertEqual(response.status_code, 200)

    def test_time_filter(self):
        started_day = pendulum.now().subtract(months=2).to_date_string()
        ended_day = pendulum.now().to_date_string()

        with freeze_time(str(pendulum.now().subtract(months=3))):
            MessageLogFactory.create_batch(5, project=self.project)

        request = self.factory.get(f"/api/{self.project.uuid}/message_history/?page_size=100&started_day={started_day}&ended_day={ended_day}")
        force_authenticate(request, user=self.user)
        response = MessageHistoryViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )
        response.render()
        content = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEquals(len(content.get("results")), 10)

    def test_tag_filter(self):
        tag = "success"

        request = self.factory.get(f"/api/{self.project.uuid}/message_history/?page_size=100&tag={tag}&started_day={self.started_day}&ended_day={self.ended_day}")
        force_authenticate(request, user=self.user)
        response = MessageHistoryViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )
        response.render()
        content = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEquals(len(content.get("results")), 10)

    def test_null_reflection_data(self):
        MessageLog.objects.all().update(reflection_data=None)

        request = self.factory.get(f"/api/{self.project.uuid}/message_history/?page_size=100&started_day={self.started_day}&ended_day={self.ended_day}")
        force_authenticate(request, user=self.user)
        response = MessageHistoryViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )
        response.render()
        content = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEquals(len(content.get("results")), 0)

    def test_empty_logs_data(self):
        MessageLog.objects.all().delete()

        request = self.factory.get(f"/api/{self.project.uuid}/message_history/?page_size=100&started_day={self.started_day}&ended_day={self.ended_day}")
        force_authenticate(request, user=self.user)
        response = MessageHistoryViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )
        response.render()
        content = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(content.get("results")), 0)


class TagPercentageViewSetTestCase(APITestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.view = TagPercentageViewSet.as_view({'get': 'list'})
        self.url = reverse('list-tag-percentage', kwargs={'project_uuid': str(self.project.uuid)})
        self.started_day = pendulum.now().subtract(months=1).to_date_string()
        self.ended_day = pendulum.now().to_date_string()

        MessageLogFactory.create_batch(5, project=self.project, reflection_data={"tag": "action_started"})
        MessageLogFactory.create_batch(3, project=self.project, reflection_data={"tag": "success"})
        MessageLogFactory.create_batch(2, project=self.project, reflection_data={"tag": "failed"})

    def test_get_tag_percentages(self):
        request = self.factory.get(self.url, {'started_day': self.started_day, 'ended_day': self.ended_day})
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=str(self.project.uuid))
        response.render()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = response.data
        self.assertIn('action_percentage', content)
        self.assertIn('succeed_percentage', content)
        self.assertIn('failed_percentage', content)

    def test_get_tag_percentages_no_logs(self):
        MessageLog.objects.all().delete()
        request = self.factory.get(self.url, {'started_day': self.started_day, 'ended_day': self.ended_day})
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=str(self.project.uuid))
        response.render()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_get_tag_percentages_invalid_date(self):
        request = self.factory.get(self.url, {'started_day': 'invalid-date', 'ended_day': self.ended_day})
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=str(self.project.uuid))
        response.render()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], "Invalid date format for started_day or ended_day")


class MessageDetailViewSetTestCase(TestCase):
    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.integrated_intelligence = create_base_brain_structure(self.project)
        self.content_base = self.integrated_intelligence.intelligence.contentbases.get()
        self.user = self.project.created_by

        chunk_evidence = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Aliquam faucibus euismod mollis."

        self.full_chunks = [
            {
                'full_page': chunk_evidence,
                'filename': 'testfile.pdf',
                'file_uuid': '87163514-b6de-4525-b16a-bf3d50e7815c'
            }
        ]

        self.reflection_data = {
            "tag": "failed",
            "request_time": 10,
            "sentence_rankings": f"Statement Sentence: Lorem ipsum dolor sit amet, consectetur adipiscing elit. Aliquam faucibus euismod mollis. Pellentesque imperdiet suscipit nisi, quis lobortis tellus convallis at. Supporting Evidence: {chunk_evidence} Score: 10",
        }
        self.llm_response = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Aliquam faucibus euismod mollis. Pellentesque imperdiet suscipit nisi."
        self.llm_model = "wenigpt:shark-1"
        self.metadata = {'agent': {'goal': 'Tirar duvidas', 'name': 'Tina', 'role': 'Atendente', 'personality': 'Amigável'}, 'instructions': []}

        self.message = Message.objects.create(
            text="Text",
            contact_urn="urn",
            status="S",
        )
        self.log = MessageLog.objects.create(
            message=self.message,
            project=self.project,
            content_base=self.content_base,
            chunks_json=self.full_chunks,
            reflection_data=self.reflection_data,
            classification="other",
            llm_response=self.llm_response,
            llm_model=self.llm_model,
            metadata=self.metadata,
            groundedness_score=10,
        )

    def test_view(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse(
            "message-detail",
            kwargs={
                "project_uuid": str(self.project.uuid),
                "log_id": str(self.message.messagelog.id)
            }
        )

        response = client.get(url, format='json')
        response.render()
        content = json.loads(response.content)

        self.assertIsNotNone(content.get("groundedness"))

    def test_view_permissions(self):
        user_401 = UserFactory()

        client = APIClient()
        client.force_authenticate(user=user_401)

        url = reverse(
            "message-detail",
            kwargs={
                "project_uuid": str(self.project.uuid),
                "log_id": str(self.message.messagelog.id)
            }
        )

        response = client.get(url, format='json')
        self.assertEquals(403, response.status_code)

    def test_view_update(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        url = reverse(
            "message-detail",
            kwargs={
                "project_uuid": str(self.project.uuid),
                "log_id": str(self.message.messagelog.id)
            }
        )
        data = {
            "is_approved": True
        }

        response = client.patch(url, format='json', data=data)
        response.render()
        content = json.loads(response.content)

        self.assertEquals(content, data)

    def test_message_action_started(self):
        action = Flow.objects.create(
            flow_uuid=str(uuid4()),
            name="Test Action",
            content_base=self.content_base,
        )
        self.message = Message.objects.create(
            text="Start Action",
            contact_urn="urn",
            status="S",
        )
        self.reflection_data = {
            "tag": "action_started",
            "action_name": action.name,
            "action_uuid": str(action.uuid)
        }

        self.log = MessageLog.objects.create(
            message=self.message,
            project=self.project,
            content_base=self.content_base,
            chunks_json=self.full_chunks,
            reflection_data=self.reflection_data,
            classification="other",
            llm_response=self.llm_response,
            llm_model=self.llm_model,
            metadata=self.metadata,
            groundedness_score=10,
        )

        client = APIClient()
        client.force_authenticate(user=self.user)

        url = reverse(
            "message-detail",
            kwargs={
                "project_uuid": str(self.project.uuid),
                "log_id": str(self.message.messagelog.id)
            }
        )

        response = client.get(url, format='json')
        response.render()
        content = json.loads(response.content)

        self.assertTrue(content.get("actions_started"))
        self.assertEquals(content.get("status"), "S")
        self.assertEquals(content.get("actions_uuid"), str(action.uuid))
        self.assertEquals(content.get("actions_type"), str(action.name))

    def test_message_action_started_old_logs(self):
        action = Flow.objects.create(
            flow_uuid=str(uuid4()),
            name="Test Action",
            content_base=self.content_base,
        )

        message = Message.objects.create(
            text="Start Action",
            contact_urn="urn",
            status="S",
        )
        reflection_data = {
            "tag": "action_started",
        }

        MessageLog.objects.create(
            message=message,
            project=self.project,
            content_base=self.content_base,
            chunks_json=self.full_chunks,
            reflection_data=reflection_data,
            classification=action.name,
            llm_response=self.llm_response,
            llm_model=self.llm_model,
            metadata=self.metadata,
            groundedness_score=0,
        )

        client = APIClient()
        client.force_authenticate(user=self.user)

        url = reverse(
            "message-detail",
            kwargs={
                "project_uuid": str(self.project.uuid),
                "log_id": str(message.messagelog.id)
            }
        )

        response = client.get(url, format='json')
        response.render()
        content = json.loads(response.content)

        self.assertTrue(content.get("actions_started"))
        self.assertEquals(content.get("status"), "F")
        self.assertEquals(content.get("actions_uuid"), str(action.uuid))
        self.assertEquals(content.get("actions_type"), str(action.name))


class InlineConversationsViewsetTestCase(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.project = ProjectFactory()
        self.user = self.project.created_by

        self.now = pendulum.now()

        # Create messages with different timestamps
        with freeze_time(str(self.now.subtract(days=2))):
            self.message1 = InlineAgentMessageFactory(
                project=self.project,
                contact_urn="tel:123456",
                source_type="user",
                source="test"
            )

        with freeze_time(str(self.now.subtract(days=1))):
            self.message2 = InlineAgentMessageFactory(
                project=self.project,
                contact_urn="tel:123456",
                source_type="agent",
                source="test"
            )

        with freeze_time(str(self.now)):
            self.message3 = InlineAgentMessageFactory(
                project=self.project,
                contact_urn="tel:123456",
                source_type="user",
                source="test"
            )

        # Create a message with different contact_urn
        self.message4 = InlineAgentMessageFactory(
            project=self.project,
            contact_urn="tel:654321",
            source_type="user",
            source="test"
        )

        # Create a message for a different project
        self.other_project = ProjectFactory()
        self.message5 = InlineAgentMessageFactory(
            project=self.other_project,
            contact_urn="tel:123456",
            source_type="user",
            source="test"
        )

        # Set date range for testing
        self.start_date = pendulum.now().subtract(days=3).to_date_string()
        self.end_date = pendulum.now().add(days=1).to_date_string()

    def test_list_inline_conversations(self):
        """Test that the view returns the correct inline messages for a contact"""
        # Use freeze_time to control the datetime for the request
        with freeze_time(self.now):
            # Use ISO datetime format
            # Set start date to before message1 and end date to after message3
            start_date = self.now.subtract(days=3).to_iso8601_string()
            end_date = self.now.add(days=1).to_iso8601_string()

            request = self.factory.get(
                f"api/{self.project.uuid}/conversations/?contact_urn=tel:123456&start={start_date}&end={end_date}"
            )
            force_authenticate(request, user=self.user)

            response = InlineConversationsViewset.as_view({'get': 'list'})(
                request,
                project_uuid=str(self.project.uuid),
            )

            response.render()
            content = json.loads(response.content)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(content.get("results")), 3)  # Should return 3 messages for tel:123456

            # Check that the messages are in the correct order (oldest created_at first)
            results = content.get("results")
            self.assertEqual(results[0].get("text"), self.message1.text)
            self.assertEqual(results[1].get("text"), self.message2.text)
            self.assertEqual(results[2].get("text"), self.message3.text)

            # Check pagination
            self.assertIn("next", content)
            self.assertIn("previous", content)

    def test_list_inline_conversations_without_end_date(self):
        """Test that the view works correctly when end_date is not provided"""
        # Use freeze_time to control the datetime for the request
        with freeze_time(self.now):
            # Use ISO datetime format with specific hour
            # Set start date to 2 days before message1's creation time to ensure it's in range
            start_date = self.now.subtract(days=2).subtract(hours=1).to_iso8601_string()

            request = self.factory.get(
                f"api/{self.project.uuid}/conversations/?contact_urn=tel:123456&start={start_date}"
            )
            force_authenticate(request, user=self.user)

            response = InlineConversationsViewset.as_view({'get': 'list'})(
                request,
                project_uuid=str(self.project.uuid),
            )

            response.render()
            content = json.loads(response.content)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(content.get("results")), 1)  # Should return only message1 since it's the only one in the range
            self.assertEqual(content.get("results")[0].get("text"), self.message1.text)

            # Verify that the end date is exactly 1 day after start with same hour
            start = pendulum.parse(start_date)
            end = start.add(days=1)
            self.assertEqual(end.hour, start.hour)
            self.assertEqual(end.minute, start.minute)

    def test_list_inline_conversations_with_different_contact(self):
        """Test that the view returns the correct inline messages for a different contact"""
        # Use ISO datetime format
        start_date = pendulum.now().subtract(days=3).to_iso8601_string()
        end_date = pendulum.now().add(days=1).to_iso8601_string()

        request = self.factory.get(
            f"api/{self.project.uuid}/conversations/?contact_urn=tel:654321&start={start_date}&end={end_date}"
        )
        force_authenticate(request, user=self.user)

        response = InlineConversationsViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )

        response.render()
        content = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(content.get("results")), 1)  # Should return 1 message for tel:654321
        self.assertEqual(content.get("results")[0].get("text"), self.message4.text)

    def test_list_inline_conversations_missing_parameters(self):
        """Test that the view returns an error when required parameters are missing"""
        # Use ISO datetime format
        start_date = pendulum.now().subtract(days=3).to_iso8601_string()
        end_date = pendulum.now().add(days=1).to_iso8601_string()

        # Missing contact_urn
        request = self.factory.get(
            f"api/{self.project.uuid}/conversations/?start={start_date}&end={end_date}"
        )
        force_authenticate(request, user=self.user)

        response = InlineConversationsViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )

        response.render()
        content = json.loads(response.content)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(content.get("error"), "Missing required parameters")

        # Missing start date
        request = self.factory.get(
            f"api/{self.project.uuid}/conversations/?contact_urn=tel:123456&end={end_date}"
        )
        force_authenticate(request, user=self.user)

        response = InlineConversationsViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )

        response.render()
        content = json.loads(response.content)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(content.get("error"), "Missing required parameters")

    def test_list_inline_conversations_unauthorized(self):
        """Test that the view requires authentication"""
        # Use ISO datetime format
        start_date = pendulum.now().subtract(days=3).to_iso8601_string()
        end_date = pendulum.now().add(days=1).to_iso8601_string()

        request = self.factory.get(
            f"api/{self.project.uuid}/conversations/?contact_urn=tel:123456&start={start_date}&end={end_date}"
        )

        response = InlineConversationsViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )

        response.render()
        self.assertEqual(response.status_code, 401)

    def test_list_inline_conversations_wrong_project(self):
        """Test that the view only returns messages for the specified project"""
        # Use ISO datetime format
        start_date = pendulum.now().subtract(days=3).to_iso8601_string()
        end_date = pendulum.now().add(days=1).to_iso8601_string()

        request = self.factory.get(
            f"api/{self.project.uuid}/conversations/?contact_urn=tel:123456&start={start_date}&end={end_date}"
        )
        force_authenticate(request, user=self.user)

        response = InlineConversationsViewset.as_view({'get': 'list'})(
            request,
            project_uuid=str(self.project.uuid),
        )

        response.render()
        content = json.loads(response.content)

        self.assertEqual(response.status_code, 200)

        # Check that we got the correct number of results (should be 3 for this project)
        results = content.get("results")
        self.assertEqual(len(results), 3)

        # Verify message5 is not in the results
        for result in results:
            self.assertNotEqual(result.get("text"), self.message5.text)
