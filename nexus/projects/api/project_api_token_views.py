import logging

import sentry_sdk
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from nexus.authentication import AUTHENTICATION_CLASSES
from nexus.projects.api.permissions import ProjectPermission
from nexus.projects.api.project_api_token_serializers import (
    ProjectApiTokenCreateRequestSerializer,
    ProjectApiTokenCreateResponseSerializer,
)
from nexus.projects.exceptions import ProjectApiTokenNameAlreadyExists, ProjectDoesNotExist
from nexus.usecases.projects.project_api_token import ProjectApiTokenUseCase

logger = logging.getLogger(__name__)


class ProjectApiTokenCreateView(APIView):
    authentication_classes = AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get_use_case(self) -> ProjectApiTokenUseCase:
        return ProjectApiTokenUseCase()

    @extend_schema(
        operation_id="create_project_api_token",
        summary="Create Project API Token",
        description=(
            "Creates a Project API Token for Supervisor public API authentication. "
            "The plaintext token is returned only once in this response."
        ),
        request=ProjectApiTokenCreateRequestSerializer,
        parameters=[
            OpenApiParameter(
                name="project_uuid",
                location=OpenApiParameter.PATH,
                required=True,
                type=OpenApiTypes.STR,
            )
        ],
        responses={
            201: OpenApiResponse(response=ProjectApiTokenCreateResponseSerializer),
            400: OpenApiResponse(description="Bad request"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Project not found"),
            409: OpenApiResponse(description="Token name already exists"),
        },
        tags=["Project API Token"],
    )
    def post(self, request, project_uuid):
        serializer = ProjectApiTokenCreateRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        try:
            use_case = self.get_use_case()
            api_token, plaintext_token = use_case.create_token(
                project_uuid=project_uuid,
                name=serializer.validated_data.get("name"),
                scope=serializer.validated_data.get("scope"),
                created_by=request.user if getattr(request.user, "is_authenticated", False) else None,
            )
            payload = use_case.serialize_created_token(api_token, plaintext_token)
            return Response(payload, status=status.HTTP_201_CREATED)
        except ProjectDoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
        except ProjectApiTokenNameAlreadyExists as exc:
            return Response({"error": exc.message}, status=status.HTTP_409_CONFLICT)
        except Exception as exc:
            logger.error("Error creating Project API Token: %s", exc, exc_info=True)
            sentry_sdk.capture_exception(exc)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
