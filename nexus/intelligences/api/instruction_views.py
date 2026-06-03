import logging

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from nexus.authentication import AUTHENTICATION_CLASSES
from nexus.feature_flags.permissions import FeatureFlagPermission
from nexus.intelligences.api.instruction_serializers import (
    ProjectInstructionsResponseSerializer,
    ProjectInstructionsUpdateSerializer,
)
from nexus.intelligences.constants import INSTRUCTION_CATEGORIZATION_FEATURE_FLAG
from nexus.intelligences.models import ContentBase, InstructionCategory
from nexus.projects.api.permissions import ProjectPermission
from nexus.usecases.intelligences import get_default_content_base_by_project
from nexus.usecases.intelligences.delete import DeleteContentBaseUseCase
from nexus.usecases.intelligences.instructions import ProjectInstructionsUseCase

logger = logging.getLogger(__name__)


class ProjectInstructionsViewSet(ModelViewSet):
    authentication_classes = AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated, ProjectPermission, FeatureFlagPermission]
    feature_flag_key = INSTRUCTION_CATEGORIZATION_FEATURE_FLAG
    use_case = ProjectInstructionsUseCase()
    delete_use_case = DeleteContentBaseUseCase()

    def get_queryset(self, *args, **kwargs):
        if getattr(self, "swagger_fake_view", False):
            return ContentBase.objects.none()  # pragma: no cover
        return ContentBase.objects.none()

    def _get_content_base(self, project_uuid):
        return get_default_content_base_by_project(project_uuid)

    @extend_schema(
        operation_id="list_project_instructions",
        summary="List project instructions grouped by category",
        parameters=[
            OpenApiParameter(
                name="project_uuid",
                location=OpenApiParameter.PATH,
                description="Project UUID",
                required=True,
                type=OpenApiTypes.STR,
            )
        ],
        responses={
            200: OpenApiResponse(response=ProjectInstructionsResponseSerializer),
            403: OpenApiResponse(description="Forbidden"),
        },
        tags=["Instructions"],
    )
    def list(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        content_base = self._get_content_base(project_uuid)
        data = self.use_case.get_grouped_instructions(content_base)
        return Response(data=data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="sync_project_instructions",
        summary="Sync project instructions grouped by category",
        request=ProjectInstructionsUpdateSerializer,
        parameters=[
            OpenApiParameter(
                name="project_uuid",
                location=OpenApiParameter.PATH,
                description="Project UUID",
                required=True,
                type=OpenApiTypes.STR,
            )
        ],
        responses={
            200: OpenApiResponse(response=ProjectInstructionsResponseSerializer),
            400: OpenApiResponse(description="Bad request"),
            403: OpenApiResponse(description="Forbidden"),
        },
        tags=["Instructions"],
    )
    def update(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        content_base = self._get_content_base(project_uuid)

        serializer = ProjectInstructionsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            data = self.use_case.sync_grouped_instructions(
                content_base=content_base,
                categories_data=serializer.validated_data["categories"],
                user=request.user,
                project_uuid=str(project_uuid),
            )
        except ValueError as error:
            return Response({"error": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as error:
            logger.error("Error syncing project instructions: %s", str(error), exc_info=True)
            return Response({"error": str(error)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(data=data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="delete_project_instruction",
        summary="Delete a project instruction",
        parameters=[
            OpenApiParameter(
                name="project_uuid",
                location=OpenApiParameter.PATH,
                description="Project UUID",
                required=True,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(
                name="id",
                location=OpenApiParameter.QUERY,
                description="Instruction ID",
                required=True,
                type=OpenApiTypes.INT,
            ),
        ],
        responses={
            200: OpenApiResponse(response=ProjectInstructionsResponseSerializer),
            403: OpenApiResponse(description="Forbidden"),
        },
        tags=["Instructions"],
    )
    def destroy(self, request, *args, **kwargs):
        instruction_id = request.query_params.get("id")
        project_uuid = kwargs.get("project_uuid")
        content_base = self._get_content_base(project_uuid)

        self.delete_use_case.bulk_delete_instruction_by_id(content_base, [instruction_id], request.user)
        data = self.use_case.get_grouped_instructions(content_base)
        return Response(data=data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="delete_project_instruction_category",
        summary="Delete a project instruction category",
        description=(
            "Deletes the category and moves its instructions to uncategorized_instructions "
            "(instructions are not deleted)."
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
                name="category_id",
                location=OpenApiParameter.PATH,
                description="Category ID",
                required=True,
                type=OpenApiTypes.INT,
            ),
        ],
        responses={
            200: OpenApiResponse(response=ProjectInstructionsResponseSerializer),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Category not found"),
        },
        tags=["Instructions"],
    )
    def destroy_category(self, request, category_id, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        content_base = self._get_content_base(project_uuid)

        try:
            data = self.use_case.delete_category(
                content_base=content_base,
                category_id=category_id,
                project_uuid=str(project_uuid),
            )
        except InstructionCategory.DoesNotExist:
            return Response({"error": "Category not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response(data=data, status=status.HTTP_200_OK)
