import logging

import pendulum
import sentry_sdk
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    OpenApiTypes,
    extend_schema,
)
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

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
    created_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField()
    topic = serializers.CharField(allow_null=True, allow_blank=True)
    channel_uuid = serializers.UUIDField(allow_null=True)
    contact_urn = serializers.CharField(allow_null=True, allow_blank=True)
    messages = MessageSerializer(many=True)


class SupervisorPublicConversationListSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = SupervisorPublicConversationItemSerializer(many=True)


class SupervisorPublicConversationsView(APIView):
    authentication_classes = [ProjectApiKeyAuthentication]
    permission_classes = [ProjectApiKeyPermission]

    @extend_schema(
        operation_id="supervisor_public_conversations",
        summary="List public supervisor conversations",
        description=(
            "Returns paginated, PII-minimized supervisor conversations for a project.\n\n"
            "Filters: start (YYYY-MM-DD), end (YYYY-MM-DD), status. Supports pagination via page and page_size."
        ),
        parameters=[
            OpenApiParameter(
                name="project_uuid",
                location=OpenApiParameter.PATH,
                description="Project UUID",
                required=True,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(
                name="start",
                location=OpenApiParameter.QUERY,
                description="Start date (YYYY-MM-DD)",
                required=False,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(
                name="end",
                location=OpenApiParameter.QUERY,
                description="End date (YYYY-MM-DD)",
                required=False,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(
                name="status",
                location=OpenApiParameter.QUERY,
                description="Resolution status",
                required=False,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(
                name="page",
                location=OpenApiParameter.QUERY,
                description="Page number",
                required=False,
                type=OpenApiTypes.INT,
            ),
            OpenApiParameter(
                name="page_size",
                location=OpenApiParameter.QUERY,
                description="Results per page",
                required=False,
                type=OpenApiTypes.INT,
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="Paginated list of conversations",
                response=SupervisorPublicConversationListSerializer,
            ),
            400: OpenApiResponse(description="Bad request"),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden"),
        },
        tags=["Supervisor Public"],
    )
    def get(self, request, project_uuid):
        try:
            qs = Conversation.objects.filter(project__uuid=project_uuid).order_by("-created_at")

            # filters
            start = request.query_params.get("start")
            end = request.query_params.get("end")
            status_param = request.query_params.get("status")

            start_dt = None
            end_dt = None
            if start:
                try:
                    start_dt = pendulum.parse(start).start_of("day")
                except Exception:
                    start_dt = start
            if end:
                try:
                    end_dt = pendulum.parse(end).end_of("day")
                except Exception:
                    end_dt = end

            # Use overlap logic so any conversation intersecting the range is included
            if start_dt and end_dt:
                qs = qs.filter(start_date__lte=end_dt, end_date__gte=start_dt)
            elif start_dt:
                qs = qs.filter(end_date__gte=start_dt)
            elif end_dt:
                qs = qs.filter(start_date__lte=end_dt)
            if status_param:
                qs = qs.filter(resolution=status_param)

            page_size = int(request.query_params.get("page_size", 50))
            page = int(request.query_params.get("page", 1))
            offset = (page - 1) * page_size
            results = []
            
            # Initialize MessageService for fetching messages
            message_service = MessageService()
            
            for conv in qs[offset : offset + page_size]:
                messages = []
                if conv.contact_urn and conv.channel_uuid and conv.start_date and conv.end_date:
                    try:
                        start_bound = start_dt or conv.start_date
                        end_bound = end_dt or conv.end_date
                        start_iso = start_bound.isoformat() if hasattr(start_bound, "isoformat") else str(start_bound)
                        end_iso = end_bound.isoformat() if hasattr(end_bound, "isoformat") else str(end_bound)
                        messages = message_service.get_messages_for_conversation(
                            project_uuid=str(project_uuid),
                            contact_urn=conv.contact_urn,
                            channel_uuid=str(conv.channel_uuid),
                            start_date=start_iso,
                            end_date=end_iso,
                            resolution_status=None,
                        )
                    except Exception as e:
                        # Log error but don't fail the entire request
                        # Messages will be empty list
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
                
                results.append(
                    {
                        "conversation_uuid": str(conv.uuid),
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
                    "count": qs.count(),
                    "page": page,
                    "page_size": page_size,
                    "results": results,
                }
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
