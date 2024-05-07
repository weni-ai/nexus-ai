import pendulum

from nexus.logs.models import Message


class DeleteLogUsecase:

    def delete_logs_routine(self, **kwargs) -> None:
        datetime = pendulum.now().subtract(**kwargs).date()
        logs = Message.objects.filter(created_at__date__lte=datetime)
        logs.delete()
