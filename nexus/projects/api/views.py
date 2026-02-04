import logging

import requests
from rest_framework import serializers, status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from nexus.projects.api.permissions import ProjectPermission
from nexus.usecases.projects.conversations import ConversationsUsecase
from nexus.usecases.projects.dto import UpdateProjectDTO
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from nexus.usecases.projects.retrieve import get_project
from nexus.usecases.projects.update import ProjectUpdateUseCase

from .serializers import ProjectSerializer

logger = logging.getLogger(__name__)


class ProjectUpdateViewset(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        user_email = request.user.email
        project = get_project(project_uuid, user_email)

        return Response(ProjectSerializer(project).data)

    def patch(self, request, project_uuid):
        user_email = request.user.email
        dto = UpdateProjectDTO(user_email, project_uuid, brain_on=request.data.get("brain_on"))
        usecase = ProjectUpdateUseCase()
        updated_project = usecase.update_project(dto)

        return Response(ProjectSerializer(updated_project).data)


class ProjectPromptCreationConfigurationsViewset(views.APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, project_uuid):
        configurations = ProjectsUseCase().get_project_prompt_creation_configurations(project_uuid=project_uuid)
        return Response(configurations)

    def patch(self, request, project_uuid):
        configurations = ProjectsUseCase().set_project_prompt_creation_configurations(
            project_uuid=project_uuid,
            use_prompt_creation_configurations=request.data.get("use_prompt_creation_configurations"),
            conversation_turns_to_include=request.data.get("conversation_turns_to_include"),
            exclude_previous_thinking_steps=request.data.get("exclude_previous_thinking_steps"),
        )

        return Response(configurations)


class AgentsBackendView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        if not project_uuid:
            return Response({"error": "project_uuid is required"}, status=400)
        try:
            agents_backend = ProjectsUseCase().get_agents_backend_by_project(project_uuid)
            return Response({"backend": agents_backend})
        except Exception as e:
            return Response({"error": str(e)}, status=404)

    def post(self, request, *args, **kwargs):
        backend = request.data.get("backend")
        project_uuid = self.kwargs.get("project_uuid")
        if not project_uuid:
            return Response({"error": "project_uuid is required"}, status=400)
        if not backend:
            return Response({"error": "backend is required"}, status=400)
        try:
            agents_backend = ProjectsUseCase().set_agents_backend_by_project(project_uuid, backend)
            return Response({"backend": agents_backend})
        except Exception as e:
            msg = str(e)
            if "Invalid backend" in msg:
                return Response({"error": msg}, status=400)
            if "does not exists" in msg or "not found" in msg:
                return Response({"error": msg}, status=404)
            return Response({"error": msg}, status=500)


class AgentBuilderProjectDetailsView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def get(self, request, *args, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        usecase = ProjectsUseCase()
        details = usecase.get_agent_builder_project_details(project_uuid)
        return Response(details)


class ConversationsProxyView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.usecase = ConversationsUsecase()

    def get(self, request, *args, **kwargs):
        """
        Proxy endpoint to fetch conversations from Conversations service.

        Query Parameters (all optional):
        - start_date: ISO Date string (>=)
        - end_date: ISO Date string (<=)
        - status: Integer mapped to resolution
        - contact_urn: String (e.g., phone number)
        - include_messages: Boolean, true returns message history
        - page: Page number for pagination
        - page_size: Number of results per page
        - limit: Limit number of results (LimitOffsetPagination)
        - offset: Offset for results (LimitOffsetPagination)

        Returns paginated response with format:
        {
            "count": int,
            "next": str or null,
            "previous": str or null,
            "results": [...]
        }
        """
        project_uuid = kwargs.get("project_uuid")

        if not project_uuid:
            return Response({"error": "project_uuid is required"}, status=status.HTTP_400_BAD_REQUEST)

        validation_error = self._validate_query_params(request)
        if validation_error:
            return validation_error

        query_params = self._extract_query_params(request)

        try:
            conversations = self.usecase.get_conversations(
                project_uuid=project_uuid,
                start_date=query_params.get("start_date"),
                end_date=query_params.get("end_date"),
                status=query_params.get("status"),
                contact_urn=query_params.get("contact_urn"),
                include_messages=query_params.get("include_messages"),
                page=query_params.get("page"),
                page_size=query_params.get("page_size"),
                limit=query_params.get("limit"),
                offset=query_params.get("offset"),
            )
            return Response(conversations, status=status.HTTP_200_OK)

        except requests.exceptions.HTTPError as e:
            return self._handle_http_error(e, project_uuid)
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.RequestException,
            serializers.ValidationError,
            Exception,
        ) as e:
            return self._handle_generic_error(e, project_uuid)

    def _validate_query_params(self, request):
        """Validate and convert query parameters."""
        include_messages = request.query_params.get("include_messages")
        status_param = request.query_params.get("status")

        if include_messages is not None:
            if include_messages.lower() not in ("true", "false"):
                return Response(
                    {"error": "include_messages must be 'true' or 'false'"}, status=status.HTTP_400_BAD_REQUEST
                )

        if status_param is not None:
            try:
                int(status_param)
            except ValueError:
                return Response({"error": "status must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        return None

    def _extract_query_params(self, request):
        """Extract and convert query parameters."""
        include_messages = request.query_params.get("include_messages")
        status_param = request.query_params.get("status")

        if include_messages is not None:
            include_messages = include_messages.lower() == "true"

        if status_param is not None:
            status_param = int(status_param)

        # Extract pagination parameters
        page = request.query_params.get("page")
        page_size = request.query_params.get("page_size")
        limit = request.query_params.get("limit")
        offset = request.query_params.get("offset")

        params = {
            "start_date": request.query_params.get("start_date"),
            "end_date": request.query_params.get("end_date"),
            "status": status_param,
            "contact_urn": request.query_params.get("contact_urn"),
            "include_messages": include_messages,
        }

        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset

        return params

    def _handle_http_error(self, e, project_uuid):
        status_code = e.response.status_code if e.response else 500
        error_message, error_details = self.usecase.extract_error_message(e.response)

        if status_code != 404:
            self.usecase.send_to_sentry(project_uuid, status_code, error_message, error_details, exception=e)

        if status_code == 400:
            return Response({"error": error_message or "Bad request"}, status=status.HTTP_400_BAD_REQUEST)
        elif status_code == 404:
            return Response(
                {"error": f"Conversations not found for project {project_uuid}"}, status=status.HTTP_404_NOT_FOUND
            )
        else:
            logger.error(
                f"Error from Conversations service for project {project_uuid}: {error_message}",
                extra={
                    "project_uuid": project_uuid,
                    "status_code": status_code,
                    "error_message": error_message,
                    "error_details": error_details,
                },
                exc_info=True,
            )
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _handle_generic_error(self, e, project_uuid):
        """Handle all other errors (connection, timeout, validation, etc.) - return generic error."""
        error_message = str(e)
        logger.error(f"Error fetching conversations for project {project_uuid}: {error_message}", exc_info=True)
        self.usecase.send_to_sentry(project_uuid, None, error_message, None, exception=e)
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
