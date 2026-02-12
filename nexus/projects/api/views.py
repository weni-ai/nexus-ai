import logging
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests
from django.conf import settings
from rest_framework import serializers, status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from nexus.projects.api.permissions import ProjectPermission
from nexus.projects.api.serializers import ConversationSerializer
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
        All query parameters are forwarded directly to the Conversations service.
        """
        project_uuid = kwargs.get("project_uuid")

        if not project_uuid:
            return Response({"error": "project_uuid is required"}, status=status.HTTP_400_BAD_REQUEST)

        query_params = {
            key: value[0] if isinstance(value, list) and len(value) == 1 else value
            for key, value in request.query_params.items()
        }

        try:
            # Call the conversations API directly with all params
            response = self._call_conversations_api(project_uuid, query_params)

            # Validate and return response using usecase logic
            if isinstance(response, dict) and "results" in response:
                serializer = ConversationSerializer(data=response["results"], many=True)
                serializer.is_valid(raise_exception=True)

                # Rewrite pagination URLs to point to nexus instead of conversations service
                next_url = self._rewrite_pagination_url(response.get("next"), request, project_uuid)
                previous_url = self._rewrite_pagination_url(response.get("previous"), request, project_uuid)

                return Response(
                    {
                        "count": response.get("count"),
                        "next": next_url,
                        "previous": previous_url,
                        "results": serializer.data,
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                serializer = ConversationSerializer(data=response, many=True)
                serializer.is_valid(raise_exception=True)
                return Response(serializer.data, status=status.HTTP_200_OK)

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

    def _call_conversations_api(self, project_uuid, query_params):
        """Call the conversations API with all query params."""
        endpoint = f"/api/v1/projects/{project_uuid}/conversations/"
        base_url = settings.CONVERSATIONS_REST_ENDPOINT
        token = settings.CONVERSATIONS_TOKEN

        url = base_url + endpoint
        headers = {
            "Content-Type": "application/json; charset: utf-8",
            "Authorization": f"Bearer {token}",
        }

        response = requests.get(url, headers=headers, params=query_params, timeout=45)
        response.raise_for_status()
        return response.json()

    def _rewrite_pagination_url(self, url, request, project_uuid):
        """Rewrite pagination URL from conversations service to nexus proxy."""
        if not url:
            return None

        try:
            # Parse the URL from conversations service
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query, keep_blank_values=True)

            # Build the nexus URL path
            nexus_path = f"/api/v2/{project_uuid}/conversations"

            # Build absolute URI using the current request
            nexus_url = request.build_absolute_uri(nexus_path)

            # Always force HTTPS scheme
            scheme = "https"

            # Add query parameters if they exist
            parsed_nexus = urlparse(nexus_url)
            if query_params:
                # urlencode with doseq=True handles lists correctly
                query_params_encoded = urlencode(query_params, doseq=True)
                nexus_url = urlunparse(
                    (
                        scheme,
                        parsed_nexus.netloc,
                        parsed_nexus.path,
                        parsed_nexus.params,
                        query_params_encoded,
                        parsed_nexus.fragment,
                    )
                )
            else:
                # Update scheme even if no query params
                nexus_url = urlunparse(
                    (
                        scheme,
                        parsed_nexus.netloc,
                        parsed_nexus.path,
                        parsed_nexus.params,
                        parsed_nexus.query,
                        parsed_nexus.fragment,
                    )
                )

            return nexus_url
        except Exception as e:
            logger.warning(f"Error rewriting pagination URL: {e}", exc_info=True)
            # Return None if there's an error, so pagination links are removed
            return None

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


class ConversationDetailProxyView(APIView):
    permission_classes = [IsAuthenticated, ProjectPermission]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.usecase = ConversationsUsecase()

    def get(self, request, *args, **kwargs):
        """
        Proxy endpoint to fetch conversation detail from Conversations service.
        """
        project_uuid = kwargs.get("project_uuid")
        conversation_uuid = kwargs.get("conversation_uuid")

        if not project_uuid:
            return Response({"error": "project_uuid is required"}, status=status.HTTP_400_BAD_REQUEST)

        if not conversation_uuid:
            return Response({"error": "conversation_uuid is required"}, status=status.HTTP_400_BAD_REQUEST)

        query_params = {
            key: value[0] if isinstance(value, list) and len(value) == 1 else value
            for key, value in request.query_params.items()
        }

        try:
            response = self._call_conversations_api(project_uuid, conversation_uuid, query_params)

            transformed_response = self._transform_response(response, request, project_uuid, conversation_uuid)

            return Response(transformed_response, status=status.HTTP_200_OK)

        except requests.exceptions.HTTPError as e:
            return self._handle_http_error(e, project_uuid, conversation_uuid)
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.RequestException,
            Exception,
        ) as e:
            return self._handle_generic_error(e, project_uuid, conversation_uuid)

    def _call_conversations_api(self, project_uuid, conversation_uuid, query_params=None):
        """Call the conversations API to get conversation detail."""
        endpoint = f"/api/v1/projects/{project_uuid}/conversations/{conversation_uuid}/"
        base_url = settings.CONVERSATIONS_REST_ENDPOINT
        token = settings.CONVERSATIONS_TOKEN

        url = base_url + endpoint
        headers = {
            "Content-Type": "application/json; charset: utf-8",
            "Authorization": f"Bearer {token}",
        }

        response = requests.get(url, headers=headers, params=query_params or {})
        response.raise_for_status()
        return response.json()

    def _transform_response(self, response_data, request, project_uuid, conversation_uuid):
        """Transform response from conversations service to SupervisorPublicConversationsView format."""
        topic = None
        if response_data.get("classification") and isinstance(response_data["classification"], dict):
            topic = response_data["classification"].get("topic")

        messages_data = response_data.get("messages", {})
        messages = {}
        if isinstance(messages_data, dict) and "results" in messages_data:
            next_url = self._rewrite_messages_pagination_url(
                messages_data.get("next"), request, project_uuid, conversation_uuid
            )
            previous_url = self._rewrite_messages_pagination_url(
                messages_data.get("previous"), request, project_uuid, conversation_uuid
            )
            messages = {
                "next": next_url,
                "previous": previous_url,
                "results": messages_data.get("results", []),
            }
        else:
            messages = messages_data if messages_data else []

        transformed = {
            "conversation_uuid": str(response_data.get("uuid")),
            "created_at": response_data.get("created_at"),
            "ended_at": response_data.get("end_date"),
            "status": response_data.get("status"),
            "topic": topic,
            "channel_uuid": str(response_data.get("channel_uuid")) if response_data.get("channel_uuid") else None,
            "contact_urn": response_data.get("contact_urn"),
            "messages": messages,
        }

        return transformed

    def _rewrite_messages_pagination_url(self, url, request, project_uuid, conversation_uuid):
        """Rewrite pagination URL from conversations service messages to nexus proxy."""
        if not url:
            return None

        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query, keep_blank_values=True)

            nexus_path = f"/api/v2/{project_uuid}/conversations/{conversation_uuid}"

            nexus_url = request.build_absolute_uri(nexus_path)

            scheme = "https"

            parsed_nexus = urlparse(nexus_url)
            if query_params:
                query_params_encoded = urlencode(query_params, doseq=True)
                nexus_url = urlunparse(
                    (
                        scheme,
                        parsed_nexus.netloc,
                        parsed_nexus.path,
                        parsed_nexus.params,
                        query_params_encoded,
                        parsed_nexus.fragment,
                    )
                )
            else:
                nexus_url = urlunparse(
                    (
                        scheme,
                        parsed_nexus.netloc,
                        parsed_nexus.path,
                        parsed_nexus.params,
                        parsed_nexus.query,
                        parsed_nexus.fragment,
                    )
                )

            return nexus_url
        except Exception as e:
            logger.warning(f"Error rewriting messages pagination URL: {e}", exc_info=True)
            return None

    def _handle_http_error(self, e, project_uuid, conversation_uuid):
        status_code = e.response.status_code if e.response else 500
        error_message, error_details = self.usecase.extract_error_message(e.response)

        if status_code != 404:
            self.usecase.send_to_sentry(project_uuid, status_code, error_message, error_details, exception=e)

        if status_code == 400:
            return Response({"error": error_message or "Bad request"}, status=status.HTTP_400_BAD_REQUEST)
        elif status_code == 404:
            return Response(
                {"error": f"Conversation {conversation_uuid} not found for project {project_uuid}"},
                status=status.HTTP_404_NOT_FOUND,
            )
        else:
            logger.error(
                f"Error from Conversations service for project {project_uuid}\
                    , conversation {conversation_uuid}: {error_message}",
                extra={
                    "project_uuid": project_uuid,
                    "conversation_uuid": conversation_uuid,
                    "status_code": status_code,
                    "error_message": error_message,
                    "error_details": error_details,
                },
                exc_info=True,
            )
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _handle_generic_error(self, e, project_uuid, conversation_uuid):
        """Handle all other errors (connection, timeout, validation, etc.) - return generic error."""
        error_message = str(e)
        logger.error(
            f"Error fetching conversation {conversation_uuid} for project {project_uuid}: {error_message}",
            exc_info=True,
        )
        self.usecase.send_to_sentry(project_uuid, None, error_message, None, exception=e)
        return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
