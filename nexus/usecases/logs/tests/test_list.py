from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate, APITestCase

from nexus.logs.models import Message, MessageLog
from nexus.logs.api.views import ConversationContextViewset

from nexus.intelligences.models import IntegratedIntelligence

from nexus.usecases.logs.list import ListLogUsecase
from nexus.usecases.intelligences.tests.intelligence_factory import LLMFactory, IntegratedIntelligenceFactory
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.logs.tests.logs_factory import MessageLogFactory


class ListLogsTestCase(TestCase):
    def setUp(self) -> None:
        self.llm = LLMFactory()
        self.project = ProjectFactory()
        self.content_base = get_default_content_base_by_project(str(self.project.uuid))

        self.llm2 = LLMFactory()
        self.project2 = ProjectFactory()
        self.content_base2 = get_default_content_base_by_project(str(self.project2.uuid))

        self.message = Message.objects.create(
            text="Test Message",
            contact_urn="tel:123321",
            status="S"
        )
        self.message2 = Message.objects.create(
            text="Test Message 2",
            contact_urn="tel:321123",
        )
        self.message3 = Message.objects.create(
            text="Test Message 3",
            contact_urn="tel:456654",
            exception="TestError"
        )

        self.log = MessageLog.objects.create(
            message=self.message,
            chunks=["Test 1", "Test 2", "Test 3"],
            prompt="Lorem Ipsum",
            project=self.project,
            content_base=self.content_base,
            classification="other",
            llm_model="test gpt",
            llm_response="Test mode",
            metadata={}
        )
        self.log2 = MessageLog.objects.create(
            message=self.message2,
            chunks=["a", "b", "c"],
            prompt="Dolor sit amet",
            project=self.project2,
            content_base=self.content_base2,
            classification="other",
            llm_model="test gpt",
            llm_response="Test mode",
            metadata={}
        )
        self.log3 = MessageLog.objects.create(
            message=self.message3,
            chunks=["1", "2", "3"],
            prompt="Lorem Ipsum",
            project=self.project,
            content_base=self.content_base,
            classification="other",
            llm_model="test gpt3",
            llm_response="Test mode",
            metadata={}
        )

    def test_list_by_project(self):
        usecase = ListLogUsecase()
        logs = usecase.list_logs_by_project(str(self.project.uuid), order_by="asc")

        self.assertEquals(logs.count(), 2)
        self.assertIsInstance(logs.first(), MessageLog)
        self.assertEquals(self.log, logs.first())

    def test_list_by_project_filter_with_kwargs(self):
        usecase = ListLogUsecase()
        logs = usecase.list_logs_by_project(str(self.project.uuid), order_by="asc", message__contact_urn="tel:456654")

        self.assertEquals(logs.count(), 1)
        self.assertIsInstance(logs.first(), MessageLog)
        self.assertEquals(self.log3, logs.first())


class ConversationContextViewsetTestCase(APITestCase):

    def setUp(self):
        ii: IntegratedIntelligence = IntegratedIntelligenceFactory()
        self.project = ii.project
        self.content_base = ii.intelligence.contentbases.first()
        self.user = self.project.created_by

        self.msg_log = MessageLogFactory.create_batch(
            10,
            project=self.project,
            content_base=self.content_base,
            classification="other",
            message__status="S",
        )
        self.factory = APIRequestFactory()
        self.view = ConversationContextViewset.as_view({'get': 'list'})
        self.url = reverse('list-conversation-context', kwargs={'project_uuid': str(self.project.uuid)})

    def test_list_last_messages(self):
        log_id = self.msg_log[-1].id
        request = self.factory.get(self.url, {'log_id': log_id, 'number_of_messages': 5})
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=str(self.project.uuid))
        response.render()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 5)
