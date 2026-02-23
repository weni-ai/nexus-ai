import logging
import math

import pendulum
import sentry_sdk
from django.db.models import Count
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
)
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from nexus.inline_agents.models import InlineAgentMessage
from nexus.intelligences.models import Conversation
from nexus.projects.api.project_api_token_auth import (
    ProjectApiKeyAuthentication,
    ProjectApiKeyPermission,
)
from router.services.message_service import MessageService

logger = logging.getLogger(__name__)


class MessageSerializer(serializers.Serializer):
    text = serializers.CharField()
    source = serializers.CharField()
    created_at = serializers.CharField()


class SupervisorPublicConversationItemSerializer(serializers.Serializer):
    conversation_uuid = serializers.UUIDField()
    start_date = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField()
    topic = serializers.CharField(allow_null=True, allow_blank=True)
    channel_uuid = serializers.UUIDField(allow_null=True)
    contact_urn = serializers.CharField(allow_null=True, allow_blank=True)
    messages = MessageSerializer(many=True)


class SupervisorPublicConversationListSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    status_summary = serializers.DictField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = SupervisorPublicConversationItemSerializer(many=True)


class SupervisorPublicConversationsView(APIView):
    authentication_classes = [ProjectApiKeyAuthentication]
    permission_classes = [ProjectApiKeyPermission]

    def _apply_filters(self, qs, request):
        start = request.query_params.get("start")
        end = request.query_params.get("end")

        start_dt = None
        end_dt = None

        try:
            if start:
                start_dt = pendulum.parse(start).start_of("day")
            if end:
                end_dt = pendulum.parse(end).end_of("day")
        except pendulum.parsing.exceptions.ParserError:
            raise ValidationError({"date": "Invalid date format. Please use ISO 8601."}) from None

        if start_dt and end_dt:
            qs = qs.filter(start_date__gte=start_dt, start_date__lte=end_dt)
        elif start_dt:
            qs = qs.filter(start_date__gte=start_dt)
        elif end_dt:
            qs = qs.filter(start_date__lte=end_dt)

        return qs, start_dt, end_dt

    def _to_utc_iso(self, val):
        try:
            return pendulum.instance(val).in_timezone("UTC").format("YYYY-MM-DDTHH:mm:ss")
        except Exception:
            return str(val)

    def _get_messages(self, conv, project_uuid, start_dt, end_dt, message_service):
        messages = []
        fetch_start = start_dt or conv.start_date
        fetch_end = end_dt or conv.end_date

        can_fetch = bool(conv.contact_urn and fetch_start and fetch_end)
        if not can_fetch:
            return messages

        try:
            start_iso = self._to_utc_iso(fetch_start)
            end_iso = self._to_utc_iso(fetch_end)

            messages = message_service.get_messages_for_conversation(
                project_uuid=str(project_uuid),
                contact_urn=conv.contact_urn,
                channel_uuid=str(conv.channel_uuid),
                start_date=start_iso,
                end_date=end_iso,
                resolution_status=None,
            )
            if not messages:
                start_utc = pendulum.instance(fetch_start).in_timezone("UTC")
                end_utc = pendulum.instance(fetch_end).in_timezone("UTC")

                inline_qs = InlineAgentMessage.objects.filter(
                    project__uuid=str(project_uuid),
                    contact_urn=conv.contact_urn,
                    created_at__range=(start_utc, end_utc),
                ).order_by("created_at")

                if inline_qs.exists():
                    messages = [
                        {
                            "text": message.text,
                            "source": "user" if message.source_type == "user" else "agent",
                            "created_at": message.created_at.isoformat(),
                        }
                        for message in inline_qs
                    ]
        except Exception as e:
            logger.warning(
                f"Error fetching messages for conversation {conv.uuid}: {str(e)}",
                extra={
                    "project_uuid": project_uuid,
                    "conversation_uuid": str(conv.uuid),
                    "contact_urn": conv.contact_urn,
                    "channel_uuid": str(conv.channel_uuid) if conv.channel_uuid else None,
                },
            )
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.set_tag("conversation_uuid", str(conv.uuid))
            sentry_sdk.capture_exception(e)
        return messages

    @extend_schema(
        summary="List Conversations",
        description="Retrieve a list of conversations for a project with optional filtering by date range and status.",
        parameters=[
            OpenApiParameter(
                name="start",
                description="Start date (ISO 8601)",
                required=False,
                type=OpenApiTypes.DATE,
            ),
            OpenApiParameter(
                name="end",
                description="End date (ISO 8601)",
                required=False,
                type=OpenApiTypes.DATE,
            ),
            OpenApiParameter(
                name="status",
                description="Filter by resolution status",
                required=False,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(
                name="page",
                description="Page number",
                required=False,
                type=OpenApiTypes.INT,
            ),
            OpenApiParameter(
                name="page_size",
                description="Number of items per page",
                required=False,
                type=OpenApiTypes.INT,
            ),
        ],
        responses={200: SupervisorPublicConversationListSerializer},
    )
    def get(self, request, project_uuid):
        try:
            qs = Conversation.objects.filter(project__uuid=project_uuid).order_by("-created_at")
            qs, start_dt, end_dt = self._apply_filters(qs, request)

            # Calculate summary stats before pagination and status filtering
            status_summary = {str(key): 0 for key, _ in Conversation.RESOLUTION_CHOICES}
            status_counts = qs.values("resolution").annotate(count=Count("resolution"))
            for item in status_counts:
                status_summary[str(item["resolution"])] = item["count"]

            status_param = request.query_params.get("status")
            if status_param:
                valid_statuses = [str(k) for k, _ in Conversation.RESOLUTION_CHOICES]
                if status_param not in valid_statuses:
                    raise ValidationError({"status": f"Invalid status. Choices are: {', '.join(valid_statuses)}"})
                qs = qs.filter(resolution=status_param)

            # Calculate summary stats before pagination
            total_count = qs.count()
            page_size = int(request.query_params.get("page_size", 50))
            if page_size < 1:
                page_size = 50
            total_pages = math.ceil(total_count / page_size) if page_size > 0 else 1

            page = int(request.query_params.get("page", 1))
            if page < 1:
                page = 1
            offset = (page - 1) * page_size
            results = []

            message_service = MessageService()
            for conv in qs[offset : offset + page_size]:
                messages = self._get_messages(conv, project_uuid, start_dt, end_dt, message_service)
                results.append(
                    {
                        "conversation_uuid": str(conv.uuid),
                        "start_date": conv.start_date.isoformat() if conv.start_date else None,
                        "created_at": conv.created_at.isoformat(),
                        "ended_at": conv.end_date.isoformat() if conv.end_date else None,
                        "status": conv.get_resolution_display(),
                        "topic": conv.get_topic() if conv.topic else None,
                        "channel_uuid": str(conv.channel_uuid) if conv.channel_uuid else None,
                        "contact_urn": conv.contact_urn,
                        "messages": messages,
                    }
                )

            return Response(
                {
                    "count": total_count,
                    "page": page,
                    "total_pages": total_pages,
                    "page_size": page_size,
                    "status_summary": status_summary,
                    "results": results,
                }
            )
        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.capture_exception(e)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
