import requests
from mozilla_django_oidc.contrib.drf import OIDCAuthentication
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from nexus.analytics.api.views import InternalCommunicationPermission
from nexus.authentication.authentication import ExternalTokenAuthentication
from nexus.internals.conversations import ConversationsRESTClient
from nexus.projects.services.projects_resolution_rate import (
    ResolutionRateQuery,
    build_response,
    eligible_projects_queryset,
    log_conversations_failure,
    parse_calendar_date,
    parse_include_blocks,
    parse_page,
    parse_page_size,
    parse_project_uuids,
    resolve_calendar_range,
)
from nexus.users.api.authentication import UserGlobalTokenAuthentication

from .resolution_rate_serializers import ProjectsResolutionRateResponseSerializer


class ProjectsResolutionRateView(APIView):
    """
    GET /api/v2/projects/resolution-rate

    Internal endpoint: conversation metrics from nexus-conversations plus project metadata from nexus-ai.
    """

    authentication_classes = [UserGlobalTokenAuthentication, ExternalTokenAuthentication, OIDCAuthentication]
    permission_classes = [InternalCommunicationPermission]

    def get(self, request):
        if getattr(self, "swagger_fake_view", False):
            return Response({})

        try:
            query = self._parse_query(request)
        except ValueError as exc:
            return self._validation_error_response(str(exc))

        projects = list(eligible_projects_queryset(query.project_uuids))
        if not projects:
            payload = build_response(query=query, summary_payload={}, projects=[])
            serializer = ProjectsResolutionRateResponseSerializer(data=payload)
            serializer.is_valid(raise_exception=True)
            return Response(payload, status=status.HTTP_200_OK)

        project_uuid_strings = [str(project.uuid) for project in projects]
        start_param = query.start_date.isoformat() if query.start_date else None
        end_param = query.end_date.isoformat() if query.end_date else None

        try:
            summary_payload = ConversationsRESTClient().get_projects_resolution_summary(
                project_uuids=project_uuid_strings,
                start_date=start_param,
                end_date=end_param,
            )
        except requests.HTTPError as exc:
            log_conversations_failure(
                project_uuids=project_uuid_strings,
                start_date=start_param,
                end_date=end_param,
                exc=exc,
            )
            return self._downstream_error_response(exc)
        except requests.RequestException as exc:
            log_conversations_failure(
                project_uuids=project_uuid_strings,
                start_date=start_param,
                end_date=end_param,
                exc=exc,
            )
            return Response(
                {"error": "Conversations service unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        payload = build_response(query=query, summary_payload=summary_payload, projects=projects)
        serializer = ProjectsResolutionRateResponseSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return Response(payload, status=status.HTTP_200_OK)

    def _parse_query(self, request) -> ResolutionRateQuery:
        raw_uuids = request.query_params.getlist("project_uuids")
        project_uuids = parse_project_uuids(raw_uuids) or None

        start_raw = request.query_params.get("start_date")
        end_raw = request.query_params.get("end_date")
        start_date = parse_calendar_date(start_raw, "start_date") if start_raw else None
        end_date = parse_calendar_date(end_raw, "end_date") if end_raw else None
        start_date, end_date = resolve_calendar_range(start_date, end_date)

        page = parse_page(request.query_params.get("page"))
        page_size = parse_page_size(request.query_params.get("page_size"))
        include_blocks = parse_include_blocks(request.query_params.get("include"))

        return ResolutionRateQuery(
            project_uuids=project_uuids,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
            include_blocks=include_blocks,
        )

    @staticmethod
    def _validation_error_response(message: str) -> Response:
        lowered = message.lower()
        if "project uuid" in lowered:
            field = "project_uuids"
        elif "start_date" in lowered and "end_date" in lowered and "both" in lowered:
            return Response({"start_date": [message], "end_date": [message]}, status=status.HTTP_400_BAD_REQUEST)
        elif "start_date" in lowered:
            field = "start_date"
        elif "end_date" in lowered:
            field = "end_date"
        elif "include" in lowered:
            field = "include"
        elif "page_size" in lowered:
            field = "page_size"
        elif "page" in lowered:
            field = "page"
        else:
            field = "detail"
        return Response({field: [message]}, status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def _downstream_error_response(exc: requests.HTTPError) -> Response:
        status_code = exc.response.status_code if exc.response is not None else status.HTTP_503_SERVICE_UNAVAILABLE
        if status_code == status.HTTP_502_BAD_GATEWAY:
            http_status = status.HTTP_502_BAD_GATEWAY
        elif status_code >= 500:
            http_status = status.HTTP_503_SERVICE_UNAVAILABLE
        else:
            http_status = status.HTTP_503_SERVICE_UNAVAILABLE
        return Response({"error": "Conversations service unavailable"}, status=http_status)
