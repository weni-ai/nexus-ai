import json

import pendulum
from freezegun import freeze_time

from django.test import TestCase

from rest_framework.test import force_authenticate
from rest_framework.test import APIRequestFactory

from nexus.usecases.intelligences.tests.intelligence_factory import LLMFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project

from nexus.logs.models import MessageLog, Message
from nexus.logs.api.serializers import MessageLogSerializer

from nexus.logs.api.views import LogsViewset


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
