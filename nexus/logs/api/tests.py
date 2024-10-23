import json

import pendulum
from freezegun import freeze_time

from django.test import TestCase

from rest_framework.test import force_authenticate
from rest_framework.test import APIRequestFactory

from nexus.usecases.intelligences.tests.intelligence_factory import LLMFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.logs.tests.logs_factory import RecentActivitiesFactory
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project

from nexus.logs.models import MessageLog, Message
from nexus.logs.api.serializers import MessageLogSerializer

from nexus.logs.api.views import LogsViewset, RecentActivitiesViewset


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
        print(message_log.data)


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
