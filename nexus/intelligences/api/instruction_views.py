import logging

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BaseRenderer
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from nexus.authentication import AUTHENTICATION_CLASSES
from nexus.feature_flags.permissions import FeatureFlagPermission
from nexus.intelligences.api.instruction_serializers import (
    ProjectInstructionsCreateSerializer,
    ProjectInstructionsPatchSerializer,
    ProjectInstructionsResponseSerializer,
)
from nexus.intelligences.constants import INSTRUCTION_CATEGORIZATION_FEATURE_FLAG
from nexus.intelligences.models import ContentBase, ContentBaseInstruction, InstructionCategory
from nexus.projects.api.permissions import ProjectPermission
from nexus.usecases.intelligences import get_default_content_base_by_project
from nexus.usecases.intelligences.delete import DeleteContentBaseUseCase
from nexus.usecases.intelligences.instructions import ProjectInstructionsUseCase

logger = logging.getLogger(__name__)


class InstructionsCSVRenderer(BaseRenderer):
    media_type = "text/csv"
    format = "csv"
    charset = "utf-8"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


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

    def get_renderers(self):
        if getattr(self, "action", None) == "export":
            return [InstructionsCSVRenderer()]
        return super().get_renderers()

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
        operation_id="export_project_instructions",
        summary="Export project instructions as CSV",
        description=(
            "Returns a CSV file with all project instructions for download. "
            "Each row contains category and instruction columns."
        ),
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
            200: OpenApiResponse(description="CSV file download"),
            403: OpenApiResponse(description="Forbidden"),
        },
        tags=["Instructions"],
    )
    def export(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        content_base = self._get_content_base(project_uuid)
        csv_content = self.use_case.build_instructions_csv(content_base)

        response = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="instructions_{project_uuid}.csv"'
        return response

    @extend_schema(
        operation_id="create_project_instruction",
        summary="Create a project instruction",
        description=(
            "Creates one instruction. Omit category or send null to store as uncategorized. "
            "Send category.id for an existing category, or category.name to create or reuse a category by name."
        ),
        request=ProjectInstructionsCreateSerializer,
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
            201: OpenApiResponse(response=ProjectInstructionsResponseSerializer),
            400: OpenApiResponse(description="Bad request"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Category not found"),
        },
        tags=["Instructions"],
    )
    def create(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        content_base = self._get_content_base(project_uuid)

        serializer = ProjectInstructionsCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            data = self.use_case.create_instruction(
                content_base=content_base,
                instruction_text=serializer.validated_data["instruction"],
                category_data=serializer.validated_data.get("category"),
                user=request.user,
                project_uuid=str(project_uuid),
            )
        except ValueError as error:
            return Response({"error": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except InstructionCategory.DoesNotExist:
            return Response({"error": "Category not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as error:
            logger.error("Error creating project instruction: %s", str(error), exc_info=True)
            return Response({"error": str(error)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(data=data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="patch_project_instructions",
        summary="Update existing project instructions and categories",
        description=(
            "Updates only existing categories and instructions (id required). "
            "Use POST to create and DELETE endpoints to remove. "
            "Omitted categories and instructions are left unchanged."
        ),
        request=ProjectInstructionsPatchSerializer,
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
    def partial_update(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        content_base = self._get_content_base(project_uuid)

        serializer = ProjectInstructionsPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            data = self.use_case.patch_grouped_instructions(
                content_base=content_base,
                categories_data=serializer.validated_data.get("categories"),
                uncategorized_data=serializer.validated_data.get("uncategorized_instructions"),
                user=request.user,
                project_uuid=str(project_uuid),
            )
        except ValueError as error:
            return Response({"error": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except ContentBaseInstruction.DoesNotExist:
            return Response({"error": "Instruction not found"}, status=status.HTTP_404_NOT_FOUND)
        except InstructionCategory.DoesNotExist:
            return Response({"error": "Category not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as error:
            logger.error("Error patching project instructions: %s", str(error), exc_info=True)
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
