from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from nexus.inline_agents.models import InlineAgentMessage
from nexus.intelligences.models import Conversation
from nexus.projects.api.project_api_token_auth import (
    ProjectApiKeyAuthentication,
    ProjectApiKeyPermission,
)


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

            if start_dt or end_dt:
                from django.db.models import Q

                date_filters = Q()
                if start_dt and end_dt:
                    date_filters |= Q(start_date__gte=start_dt, start_date__lte=end_dt)
                    date_filters |= Q(start_date__isnull=True, created_at__gte=start_dt, created_at__lte=end_dt)
                elif start_dt:
                    date_filters |= Q(start_date__gte=start_dt) | Q(start_date__isnull=True, created_at__gte=start_dt)
                elif end_dt:
                    date_filters |= Q(start_date__lte=end_dt) | Q(start_date__isnull=True, created_at__lte=end_dt)

                qs = qs.filter(date_filters)
            if status_param:
                qs = qs.filter(resolution=status_param)

            page_size = int(request.query_params.get("page_size", 50))
            page = int(request.query_params.get("page", 1))
            offset = (page - 1) * page_size
            results = []
            for conv in qs[offset : offset + page_size]:
                results.append(
                    {
                        "conversation_uuid": str(conv.uuid),
                        "created_at": conv.created_at.isoformat(),
                        "ended_at": conv.end_date.isoformat() if conv.end_date else None,
                        "status": conv.get_resolution_display(),
                        "topic": conv.get_topic() if conv.topic else None,
                        "channel_uuid": str(conv.channel_uuid) if conv.channel_uuid else None,
                        # minimize PII exposure
                        "contact_urn": None,
                        "contact_name": None,
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
