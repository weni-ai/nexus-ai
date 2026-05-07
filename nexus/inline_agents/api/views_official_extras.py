"""Official agents API endpoints kept separate from views.py to limit module size."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from nexus.authentication import AUTHENTICATION_CLASSES
from nexus.inline_agents.api.serializers import OfficialAvailableSystemsEnvelopeSerializer
from nexus.inline_agents.api.services.available_systems import available_systems_response_data
from nexus.projects.api.permissions import CombinedExternalProjectPermission


class OfficialAvailableSystemsV1(APIView):
    """Global AgentSystem catalog."""

    authentication_classes = AUTHENTICATION_CLASSES
    permission_classes = [CombinedExternalProjectPermission]

    @extend_schema(
        operation_id="v1_official_available_systems",
        summary="List agent integration systems",
        description=(
            "Returns all agent systems with slug, name, and logo URL (same payload previously "
            "returned as ``new.available_systems`` on GET /api/v1/official/agents)."
        ),
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
