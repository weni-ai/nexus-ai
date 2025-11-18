import warnings

import pendulum
from django.test import TestCase
from freezegun import freeze_time

from nexus.usecases.logs.tests.logs_factory import RecentActivitiesFactory

from ..models import RecentActivities


class TestRecentActivitiesTasks(TestCase):
    def setUp(self) -> None:
        # Suppress the naive datetime warning from Django's auto_now_add field
        warnings.filterwarnings(
            "ignore", message="DateTimeField.*received a naive datetime.*while time zone support is active"
        )

        self.new_recent_activities = RecentActivitiesFactory()

        date_to_exclude = pendulum.now("UTC").subtract(months=4).to_iso8601_string()
        with freeze_time(date_to_exclude):
            self.logs_batch = RecentActivitiesFactory.create_batch(size=10)

    def test_delete_old_activities(self):
        before_delete = RecentActivities.objects.count()
        # Call the task directly to ensure synchronous execution
        from nexus.task_managers.tasks import delete_old_activities

        delete_old_activities()
        after_delete = RecentActivities.objects.count()
        self.assertEqual(before_delete, 11)
        self.assertEqual(1, after_delete)
