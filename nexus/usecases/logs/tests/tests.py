import pendulum
from freezegun import freeze_time

from django.test import TestCase
from nexus.logs.models import Message, MessageLog

from nexus.usecases.logs.delete import DeleteLogUsecase
from nexus.usecases.logs.list import ListLogUsecase

from nexus.usecases.intelligences.tests.intelligence_factory import LLMFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.intelligences.get_by_uuid import get_default_content_base_by_project


class DeleteLogsTestCase(TestCase):

    def create_logs(self):
        with freeze_time(str(pendulum.now().subtract(months=1))):
            message = Message.objects.create(
                text="Text 1",
                contact_urn="contact_urn",
                status="S"
            )
            MessageLog.objects.create(
                message=message,
            )

        with freeze_time(str(pendulum.now().subtract(days=2))):
            message = Message.objects.create(
                text="Text 2",
                contact_urn="contact_urn",
                status="S"
            )
            MessageLog.objects.create(
                message=message,
            )

        message = Message.objects.create(
            text="Text 3",
            contact_urn="contact_urn",
            status="S"
        )
        MessageLog.objects.create(
            message=message,
            created_at=pendulum.now()
        )

    def setUp(self) -> None:
        self.create_logs()

    def test_delete_log_routine(self):
        usecase = DeleteLogUsecase()
        usecase.delete_logs_routine(months=1)
        self.assertEquals(MessageLog.objects.count(), 2)
        self.assertEquals(Message.objects.count(), 2)


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
