import logging

import pendulum

from nexus.logs.models import Message, RecentActivities


class DeleteLogUsecase:
    def delete_logs_routine(self, **kwargs) -> None:
        datetime = pendulum.now().subtract(**kwargs).date()
        logs = Message.objects.filter(created_at__date__lte=datetime)
        logs.delete()

    def delete_old_activities(self, **kwargs) -> None:
        datetime = pendulum.now().subtract(**kwargs).date()
        old_activities = RecentActivities.objects.filter(created_at__lt=datetime)
        count = old_activities.count()
        old_activities.delete()
        logging.getLogger(__name__).info("Deleted old RecentActivities", extra={"count": count})
