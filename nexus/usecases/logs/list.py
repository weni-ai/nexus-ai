from datetime import datetime

from django.db.models import QuerySet
from django.core.exceptions import FieldError

from nexus.logs.models import MessageLog
from nexus.inline_agents.models import InlineAgentMessage
from router.services.message_service import MessageService


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
        ).order_by("created_at")

        return messages

    def list_messages_for_conversation(
        self,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: str,
        start: datetime,
        end: datetime
    ):
        """
        Get all messages for a specific conversation period using DynamoDB repository.
        This method retrieves all messages within the time period, regardless of resolution status.

        Args:
            project_uuid: Project unique identifier
            contact_urn: Contact unique resource name
            channel_uuid: Channel unique identifier
            start: Start datetime for conversation period
            end: End datetime for conversation period

        Returns:
            List of all messages within the conversation period
        """
        # Initialize MessageService with default DynamoDB repository
        message_service = MessageService()

        # Convert datetime objects to ISO strings for DynamoDB queries
        start_iso = start.isoformat()
        end_iso = end.isoformat()

        # Get all messages for the conversation period (no resolution filtering)
        messages = message_service.get_messages_for_conversation(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            start_date=start_iso,
            end_date=end_iso,
            resolution_status=None  # No resolution filtering - get all messages
        )

        return messages
