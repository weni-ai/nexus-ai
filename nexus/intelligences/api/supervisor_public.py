import logging

import pendulum
import sentry_sdk
from rest_framework import serializers, status
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

            if start_dt and end_dt:
                qs = qs.filter(start_date__gte=start_dt, start_date__lte=end_dt)
            elif start_dt:
                qs = qs.filter(start_date__gte=start_dt)
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
                fetch_start = start_dt or conv.start_date
                fetch_end = end_dt or conv.end_date

                can_fetch = bool(conv.contact_urn and fetch_start and fetch_end)
                if can_fetch:
                    try:

                        def _to_utc_iso(val):
                            try:
                                return pendulum.parse(str(val)).in_timezone("UTC").format("YYYY-MM-DDTHH:mm:ss")
                            except Exception:
                                return str(val)

                        start_iso = _to_utc_iso(fetch_start)
                        end_iso = _to_utc_iso(fetch_end)
                        messages = message_service.get_messages_for_conversation(
                            project_uuid=str(project_uuid),
                            contact_urn=conv.contact_urn,
                            channel_uuid=str(conv.channel_uuid),
                            start_date=start_iso,
                            end_date=end_iso,
                            resolution_status=None,
                        )
                        if not messages:
                            inline_qs = InlineAgentMessage.objects.filter(
                                project__uuid=str(project_uuid),
                                contact_urn=conv.contact_urn,
                                created_at__range=(
                                    pendulum.parse(start_iso).in_timezone("UTC"),
                                    pendulum.parse(end_iso).in_timezone("UTC"),
                                ),
                            ).order_by("created_at")
                            if inline_qs.exists():
                                messages = [
                                    {
                                        "text": m.text,
                                        "source": "user" if m.source_type == "user" else "agent",
                                        "created_at": m.created_at.isoformat(),
                                    }
                                    for m in inline_qs
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
