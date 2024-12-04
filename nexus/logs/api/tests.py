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

from nexus.logs.models import MessageLog, Message
from nexus.logs.api.serializers import MessageLogSerializer

from nexus.logs.api.views import (
    LogsViewset,
    RecentActivitiesViewset,
    MessageHistoryViewset,
    TagPercentageViewSet
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
        self.assertEquals(len(content.get("results")), 0)

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

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error'], "No logs found for the given date range")

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
        self.assertEquals(content.get("status"), "F")
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
