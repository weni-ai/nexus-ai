from django.db.models import QuerySet
from django.core.exceptions import FieldError
from nexus.logs.models import MessageLog


class ListLogUsecase:
    def list_logs_by_project(self, project_uuid: str, **kwargs) -> QuerySet[MessageLog]:
        logs = MessageLog.objects.filter(project__uuid=project_uuid)

        if kwargs:
            try:
                logs = logs.filter(**kwargs)
            except FieldError:
                return logs

        return logs
