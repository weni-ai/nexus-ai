import requests
from django.conf import settings

from nexus.internals import RestClient


class ConversationsRESTClient(RestClient):
    def __init__(self):
        self.base_url = settings.CONVERSATIONS_REST_ENDPOINT
        self.token = settings.CONVERSATIONS_TOKEN

    def _get_url(self, endpoint: str) -> str:
        assert endpoint.startswith("/"), "the endpoint needs to start with: /"
        return self.base_url + endpoint

    @property
    def headers(self):
        return {
            "Content-Type": "application/json; charset: utf-8",
            "Authorization": f"Bearer {self.token}",
        }

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
                "results": [conversation objects]
            }
        """
        endpoint = f"/api/v1/projects/{project_uuid}/conversations/"
        params = {}

        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date
        if status is not None:
            params["status"] = status
        if contact_urn is not None:
            params["contact_urn"] = contact_urn
        if include_messages is not None:
            params["include_messages"] = include_messages
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset

        response = requests.get(
            self._get_url(endpoint),
            headers=self.headers,
            params=params if params else None,
        )
        response.raise_for_status()
        return response.json()
