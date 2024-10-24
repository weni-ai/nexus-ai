import json

import pendulum
from freezegun import freeze_time

from django.test import TestCase
from django.urls import reverse

from rest_framework.test import APIRequestFactory, force_authenticate, APITestCase
from rest_framework import status

from nexus.usecases.intelligences.tests.intelligence_factory import LLMFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.logs.tests.logs_factory import RecentActivitiesFactory, MessageLogFactory
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project

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
        tag = "failed"

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
