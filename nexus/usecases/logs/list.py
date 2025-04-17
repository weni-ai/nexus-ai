from datetime import datetime

from django.db.models import QuerySet
from django.core.exceptions import FieldError

from nexus.logs.models import MessageLog
from nexus.inline_agents.models import InlineAgentMessage


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

    def list_last_logs(
        self,
        log_id: int,
        message_count: int = 5,
    ):
        log = MessageLog.objects.get(id=log_id)
        project = log.project
        source = log.source
        contact_urn = log.message.contact_urn
        created_at = log.created_at

        logs = MessageLog.objects.filter(
            project=project,
            source=source,
            message__contact_urn=contact_urn,
            created_at__lt=created_at
        ).order_by("-created_at")[:message_count]

        logs = list(logs)[::-1]

        return logs

    def list_last_inline_messages(
        self,
        project_uuid: str,
        contact_urn: str,
        start: datetime,
        end: datetime,
    ):
        messages = InlineAgentMessage.objects.filter(
            project__uuid=project_uuid,
            contact_urn=contact_urn,
            created_at__range=(start, end)
        ).order_by("-created_at")

        return messages
