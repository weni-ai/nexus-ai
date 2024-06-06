import pendulum
from freezegun import freeze_time

from django.test import TestCase

from .logs_factory import RecentActivitiesFactory

from nexus.logs.models import Message, MessageLog, RecentActivities
from nexus.usecases.logs.delete import DeleteLogUsecase


class DeleteMessageLogsTestCase(TestCase):

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


class DeleteOldActivitiesTestCase(TestCase):
    def setUp(self) -> None:
        RecentActivitiesFactory()
        with freeze_time(str(pendulum.now('UTC').subtract(months=4))):
            RecentActivitiesFactory.create_batch(
                size=10,
            )

    def test_delete_old_activities(self):
        before_delete = RecentActivities.objects.count()
        usecase = DeleteLogUsecase()
        usecase.delete_old_activities(months=3)
        after_delete = RecentActivities.objects.count()
        self.assertEqual(before_delete, 11)
        self.assertEqual(1, after_delete)
