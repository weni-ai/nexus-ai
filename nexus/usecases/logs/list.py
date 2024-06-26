from django.db.models import QuerySet
from django.core.exceptions import FieldError
from nexus.logs.models import MessageLog


class ListLogUsecase:
    def list_logs_by_project(self, project_uuid: str, order_by: str, **kwargs) -> QuerySet[MessageLog]:
        if order_by.lower() == "desc":
            order = "-created_at"
        else:
            order = "created_at"

        logs = MessageLog.objects.select_related("message").filter(project__uuid=project_uuid)

        if kwargs:
            try:
                logs = logs.filter(**kwargs)
            except FieldError:
                return logs

        return logs.order_by(order)
