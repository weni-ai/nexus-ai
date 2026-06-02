"""Official agents API endpoints kept separate from views.py to limit module size."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from nexus.authentication import AUTHENTICATION_CLASSES
from nexus.inline_agents.api.serializers import OfficialAvailableSystemsEnvelopeSerializer
from nexus.inline_agents.api.services.available_systems import available_systems_response_data
from nexus.projects.api.permissions import CombinedExternalProjectPermission


class OfficialAvailableSystemsV1(APIView):
    """AgentSystem catalog for official integrations (same data model as the former embedded list field)."""

    authentication_classes = AUTHENTICATION_CLASSES
    permission_classes = [CombinedExternalProjectPermission]

    @extend_schema(
        operation_id="v1_official_available_systems",
        summary="List agent integration systems",
        description=(
            "Returns all agent systems with slug, name, and logo URL (same payload previously "
            "**Authorization:** Uses ``CombinedExternalProjectPermission``. With a normal "
            "project-scoped Bearer token you MUST pass ``project_uuid`` as a query parameter "
            "(same as GET /api/v1/official/agents) so ``ProjectPermission`` can resolve access. "
            "Tokens listed in ``settings.EXTERNAL_SUPERUSERS_TOKENS`` may call this endpoint without "
            "``project_uuid``."
        ),
        parameters=[
            OpenApiParameter(
                name="project_uuid",
                location=OpenApiParameter.QUERY,
                required=False,
                type=OpenApiTypes.UUID,
                description=(
                    "Project UUID for permission checks when using a non-superuser Bearer token. "
                    "Omit only when using an external superuser token."
                ),
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="Available systems",
                response=OfficialAvailableSystemsEnvelopeSerializer,
            ),
            401: OpenApiResponse(description="Unauthorized"),
            403: OpenApiResponse(description="Forbidden"),
        },
        tags=["Agents"],
    )
    def get(self, request, *args, **kwargs):
        return Response(available_systems_response_data())
