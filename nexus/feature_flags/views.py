from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from weni.feature_flags.services import FeatureFlagsService

from nexus.feature_flags.serializers import FeatureFlagsQueryParamsSerializer
from nexus.projects.api.permissions import ProjectPermission


class FeatureFlagsViewSet(GenericViewSet):
    """Return active GrowthBook feature flags for the authenticated user and project."""

    service = FeatureFlagsService()
    permission_classes = [IsAuthenticated, ProjectPermission]
    serializer_class = FeatureFlagsQueryParamsSerializer

    def list(self, request, *args, **kwargs) -> Response:
        query_params = FeatureFlagsQueryParamsSerializer(data=request.query_params)
        query_params.is_valid(raise_exception=True)

        project = query_params.validated_data["project"]
        attributes = {"weni_project": str(project.uuid)}

        active_features = self.service.get_active_feature_flags_for_attributes(
            attributes=attributes,
        )

        return Response({"active_features": active_features}, status=status.HTTP_200_OK)
