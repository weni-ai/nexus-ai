import logging

import sentry_sdk

from nexus.internals.conversations import ConversationsRESTClient
from nexus.projects.api.serializers import ConversationSerializer

logger = logging.getLogger(__name__)


class ConversationsUsecase:
    def __init__(self, client=None):
        self.client = client or ConversationsRESTClient()

    def get_conversations(
        self,
        project_uuid: str,
        start_date: str = None,
        end_date: str = None,
        status: int = None,
        contact_urn: str = None,
        include_messages: bool = None,
        page: str = None,
        page_size: str = None,
        limit: str = None,
        offset: str = None,
    ):
        """
        Get conversations for a project with optional filters and pagination.

        Args:
            project_uuid: UUID of the project (required)
            start_date: ISO Date string (>=) - optional
            end_date: ISO Date string (<=) - optional
            status: Integer mapped to resolution - optional
            contact_urn: String (e.g., phone number) - optional
            include_messages: Boolean, True returns message history - optional
            page: Page number for pagination - optional
            page_size: Number of results per page - optional
            limit: Limit number of results (LimitOffsetPagination) - optional
            offset: Offset for results (LimitOffsetPagination) - optional

        Returns:
            Paginated response dict with format:
            {
                "count": int,
                "next": str or null,
                "previous": str or null,
                "results": [validated conversation objects]
            }

        Raises:
            requests.exceptions.HTTPError: For HTTP errors from Conversations service
            requests.exceptions.RequestException: For other request errors
            serializers.ValidationError: For validation errors in response
        """
        response = self.client.get_conversations(
            project_uuid=project_uuid,
            start_date=start_date,
            end_date=end_date,
            status=status,
            contact_urn=contact_urn,
            include_messages=include_messages,
            page=page,
            page_size=page_size,
            limit=limit,
            offset=offset,
        )

        if isinstance(response, dict) and "results" in response:
            # Validate only the results array
            serializer = ConversationSerializer(data=response["results"], many=True)
            serializer.is_valid(raise_exception=True)

            return {
                "count": response.get("count"),
                "next": response.get("next"),
                "previous": response.get("previous"),
                "results": serializer.data,
            }
        else:
            serializer = ConversationSerializer(data=response, many=True)
            serializer.is_valid(raise_exception=True)
            return serializer.data

    def extract_error_message(self, response):
        """Extract error message from HTTP response."""
        error_message = str(response)
        error_details = None

        if response:
            try:
                response_data = response.json()
                if isinstance(response_data, dict):
                    error_message = response_data.get("error") or response_data.get("message") or str(response)
                    error_details = response_data
                elif isinstance(response_data, str):
                    error_message = response_data
            except (ValueError, AttributeError):
                error_message = response.text or str(response)

        return error_message, error_details

    def send_to_sentry(self, project_uuid, status_code, error_message, error_details, exception=None):
        """Centralized method to send error information to Sentry."""
        sentry_sdk.set_tag("project_uuid", project_uuid)

        context = {
            "project_uuid": project_uuid,
            "error_message": error_message,
        }

        if status_code is not None:
            context["status_code"] = status_code
            sentry_sdk.set_tag("conversations_status_code", status_code)

        if error_details:
            context["error_details"] = error_details

        sentry_sdk.set_context("conversations_error", context)

        if exception:
            sentry_sdk.capture_exception(exception)
        else:
            sentry_sdk.capture_message(f"Conversations service error: {error_message}", level="error")
