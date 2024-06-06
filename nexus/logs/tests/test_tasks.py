import pendulum
from freezegun import freeze_time
from django.test import TestCase

from ..models import RecentActivities

from nexus.celery import app
from nexus.usecases.logs.tests.logs_factory import RecentActivitiesFactory


class test_recent_activities_tasks(TestCase):

    def setUp(self) -> None:
        self.new_recent_activities = RecentActivitiesFactory()

        date_to_exclude = str(pendulum.now().subtract(months=4))
        with freeze_time(date_to_exclude):
            self.logs_batch = RecentActivitiesFactory.create_batch(
                size=10
            )

    def test_delete_old_activities(self):
        before_delete = RecentActivities.objects.count()
        app.send_task(name="delete_old_activities")
        after_delete = RecentActivities.objects.count()
        self.assertEqual(before_delete, 11)
        self.assertEqual(1, after_delete)
