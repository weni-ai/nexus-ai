import logging

import sentry_sdk
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from nexus.authentication import AUTHENTICATION_CLASSES
from nexus.projects.api.permissions import ProjectPermission
from nexus.projects.api.resolution_criteria_serializers import (
    AIResolutionCriteriaCreateRequestSerializer,
    AIResolutionCriteriaDeleteResponseSerializer,
    AIResolutionCriteriaListResponseSerializer,
    AIResolutionCriteriaUpdateRequestSerializer,
    AIResolutionCriteriaValidateRequestSerializer,
    AIResolutionCriteriaValidateResponseSerializer,
    AIResolutionCriterionItemSerializer,
)
from nexus.projects.exceptions import (
    LambdaValidationFailedError,
    ProjectDoesNotExist,
    ResolutionCriterionNotFound,
    ResolutionCriterionValidationError,
    UnauthorizedBaseCriterionChange,
)
from nexus.usecases.projects.ai_resolution_criteria import AIResolutionCriteriaUseCase

logger = logging.getLogger(__name__)


class AIResolutionCriteriaListCreateView(APIView):
    authentication_classes = AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated, ProjectPermission]
    use_case = AIResolutionCriteriaUseCase()

    @extend_schema(
        operation_id="list_ai_resolution_criteria",
        summary="List AI resolution criteria",
        parameters=[
            OpenApiParameter(
                name="project_uuid",
                location=OpenApiParameter.PATH,
                required=True,
                type=OpenApiTypes.STR,
            )
        ],
        responses={
            200: OpenApiResponse(response=AIResolutionCriteriaListResponseSerializer),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Project not found"),
        },
        tags=["AI Resolution Criteria"],
    )
    def get(self, request, project_uuid):
        try:
            data = self.use_case.list_criteria(project_uuid)
            return Response(data, status=status.HTTP_200_OK)
        except ProjectDoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.error("Error listing AI resolution criteria: %s", exc, exc_info=True)
            sentry_sdk.capture_exception(exc)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        operation_id="create_ai_resolution_criterion",
        summary="Create custom AI resolution criterion",
        request=AIResolutionCriteriaCreateRequestSerializer,
        parameters=[
            OpenApiParameter(
                name="project_uuid",
                location=OpenApiParameter.PATH,
                required=True,
                type=OpenApiTypes.STR,
            )
        ],
        responses={
            201: OpenApiResponse(response=AIResolutionCriterionItemSerializer),
            400: OpenApiResponse(description="Bad request"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Project not found"),
        },
        tags=["AI Resolution Criteria"],
    )
    def post(self, request, project_uuid):
        serializer = AIResolutionCriteriaCreateRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": "Text is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            data = self.use_case.create_criterion(
                project_uuid=project_uuid,
                text=serializer.validated_data["text"],
                user=request.user,
            )
            return Response(data, status=status.HTTP_201_CREATED)
        except ValueError:
            return Response({"error": "Text is required"}, status=status.HTTP_400_BAD_REQUEST)
        except ProjectDoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.error("Error creating AI resolution criterion: %s", exc, exc_info=True)
            sentry_sdk.capture_exception(exc)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AIResolutionCriteriaValidateView(APIView):
    authentication_classes = AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated, ProjectPermission]
    use_case = AIResolutionCriteriaUseCase()

    @extend_schema(
        operation_id="validate_ai_resolution_criterion",
        summary="Validate AI resolution criterion via Lambda",
        request=AIResolutionCriteriaValidateRequestSerializer,
        parameters=[
            OpenApiParameter(
                name="project_uuid",
                location=OpenApiParameter.PATH,
                required=True,
                type=OpenApiTypes.STR,
            )
        ],
        responses={
            200: OpenApiResponse(response=AIResolutionCriteriaValidateResponseSerializer),
            400: OpenApiResponse(description="Validation rejected"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Project or criterion not found"),
            502: OpenApiResponse(description="Lambda validation failed"),
        },
        tags=["AI Resolution Criteria"],
    )
    def post(self, request, project_uuid):
        serializer = AIResolutionCriteriaValidateRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": "Text is required"}, status=status.HTTP_400_BAD_REQUEST)

        criterion_id = serializer.validated_data.get("criterion_id")
        try:
            data = self.use_case.validate_criterion(
                project_uuid=project_uuid,
                text=serializer.validated_data["text"],
                criterion_id=str(criterion_id) if criterion_id else None,
            )
            return Response(data, status=status.HTTP_200_OK)
        except ValueError:
            return Response({"error": "Text is required"}, status=status.HTTP_400_BAD_REQUEST)
        except ResolutionCriterionValidationError as exc:
            return Response(
                {"error": {"code": exc.code, "message": exc.message}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ResolutionCriterionNotFound:
            return Response(
                {"error": {"code": "CRITERION_NOT_FOUND", "message": "Criterion not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        except UnauthorizedBaseCriterionChange:
            return Response(
                {
                    "error": {
                        "code": "UNAUTHORIZED_BASE_CRITERION_CHANGE",
                        "message": "Base criteria cannot be modified",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except LambdaValidationFailedError as exc:
            return Response(
                {"error": {"code": "LAMBDA_VALIDATION_FAILED", "message": exc.message}},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except ProjectDoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.error("Error validating AI resolution criterion: %s", exc, exc_info=True)
            sentry_sdk.capture_exception(exc)
            return Response(
                {
                    "error": {
                        "code": "LAMBDA_VALIDATION_FAILED",
                        "message": "The criterion could not be validated due to a technical issue",
                    }
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )


class AIResolutionCriteriaDetailView(APIView):
    authentication_classes = AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated, ProjectPermission]
    use_case = AIResolutionCriteriaUseCase()

    @extend_schema(
        operation_id="update_ai_resolution_criterion",
        summary="Update custom AI resolution criterion",
        request=AIResolutionCriteriaUpdateRequestSerializer,
        parameters=[
            OpenApiParameter(
                name="project_uuid",
                location=OpenApiParameter.PATH,
                required=True,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(
                name="criterion_id",
                location=OpenApiParameter.PATH,
                required=True,
                type=OpenApiTypes.STR,
            ),
        ],
        responses={
            200: OpenApiResponse(response=AIResolutionCriterionItemSerializer),
            400: OpenApiResponse(description="Bad request"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Criterion not found"),
        },
        tags=["AI Resolution Criteria"],
    )
    def patch(self, request, project_uuid, criterion_id):
        serializer = AIResolutionCriteriaUpdateRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": "Text is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            data = self.use_case.update_criterion(
                project_uuid=project_uuid,
                criterion_id=criterion_id,
                text=serializer.validated_data["text"],
                user=request.user,
            )
            return Response(data, status=status.HTTP_200_OK)
        except ValueError:
            return Response({"error": "Text is required"}, status=status.HTTP_400_BAD_REQUEST)
        except UnauthorizedBaseCriterionChange:
            return Response(
                {
                    "error": {
                        "code": "UNAUTHORIZED_BASE_CRITERION_CHANGE",
                        "message": "Base criteria cannot be modified",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except ResolutionCriterionNotFound:
            return Response(
                {"error": {"code": "CRITERION_NOT_FOUND", "message": "Criterion not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ProjectDoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.error("Error updating AI resolution criterion: %s", exc, exc_info=True)
            sentry_sdk.capture_exception(exc)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        operation_id="delete_ai_resolution_criterion",
        summary="Delete custom AI resolution criterion",
        parameters=[
            OpenApiParameter(
                name="project_uuid",
                location=OpenApiParameter.PATH,
                required=True,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(
                name="criterion_id",
                location=OpenApiParameter.PATH,
                required=True,
                type=OpenApiTypes.STR,
            ),
        ],
        responses={
            200: OpenApiResponse(response=AIResolutionCriteriaDeleteResponseSerializer),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Criterion not found"),
        },
        tags=["AI Resolution Criteria"],
    )
    def delete(self, request, project_uuid, criterion_id):
        try:
            self.use_case.delete_criterion(project_uuid=project_uuid, criterion_id=criterion_id)
            return Response({"success": True}, status=status.HTTP_200_OK)
        except UnauthorizedBaseCriterionChange:
            return Response(
                {
                    "error": {
                        "code": "UNAUTHORIZED_BASE_CRITERION_CHANGE",
                        "message": "Base criteria cannot be modified",
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        except ResolutionCriterionNotFound:
            return Response(
                {"error": {"code": "CRITERION_NOT_FOUND", "message": "Criterion not found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ProjectDoesNotExist:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
            logger.error("Error deleting AI resolution criterion: %s", exc, exc_info=True)
            sentry_sdk.capture_exception(exc)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
