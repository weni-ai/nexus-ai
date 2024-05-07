import pendulum
from freezegun import freeze_time

from django.test import TestCase
from nexus.logs.models import Message, MessageLog

from nexus.usecases.logs.delete import DeleteLogUsecase


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
