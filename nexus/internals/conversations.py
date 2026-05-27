from urllib.parse import urljoin

import requests
from django.conf import settings

from nexus.internals import RestClient


class ConversationsRESTClient(RestClient):
    def __init__(self):
        self.base_url = settings.CONVERSATIONS_REST_ENDPOINT
        self.token = settings.CONVERSATIONS_TOKEN

    def _get_url(self, endpoint: str) -> str:
        assert endpoint.startswith("/"), "the endpoint needs to start with: /"
        return self.base_url.rstrip("/") + endpoint

    @property
    def headers(self):
        return {
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
            timeout=45,
        )
        response.raise_for_status()
        return response.json()

    def get_projects_resolution_summary(
        self,
        *,
        project_uuids: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        timeout: int = 60,
    ) -> dict:
        """
        Aggregated resolution, CSAT and NPS metrics for multiple projects (internal endpoint).
        """
        endpoint = "/api/v1/projects/resolution-summary/"
        params: list[tuple[str, str]] = []
        if start_date is not None:
            params.append(("start_date", start_date))
        if end_date is not None:
            params.append(("end_date", end_date))
        if project_uuids:
            for project_uuid in project_uuids:
                params.append(("project_uuids", project_uuid))

        response = requests.get(
            self._get_url(endpoint),
            headers=self.headers,
            params=params or None,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_reconcile_cohort(
        self,
        project_uuid: str,
        *,
        date_start: str,
        date_end: str,
        apply_terminal_cohort_filter: bool = True,
        timeout: int = 300,
    ) -> dict:
        """
        Fetch DB cohort rows for Flows reconcile (internal conversations endpoint).
        """
        endpoint = f"/api/v1/projects/{project_uuid}/reconcile-cohort/"
        response = requests.get(
            self._get_url(endpoint),
            headers=self.headers,
            params={
                "date_start": date_start,
                "date_end": date_end,
                "apply_terminal_cohort_filter": apply_terminal_cohort_filter,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_topics(self, project_uuid: str):
        """Fetch all topics for a project, iterating through all pages."""
        endpoint = f"/api/v1/projects/{project_uuid}/topics/"
        all_results = []
        url = self._get_url(endpoint)

        while url:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=45,
            )
            response.raise_for_status()
            data = response.json()
            all_results.extend(data.get("results", []))
            next_url = data.get("next")
            url = urljoin(self.base_url, next_url) if next_url else None

        return all_results

    def export_conversations_csv(self, project_uuid: str, target_date: str | None = None):
        """
        POST export endpoint; returns the raw requests.Response (CSV body + headers).
        """
        endpoint = f"/api/v1/projects/{project_uuid}/conversations/export/"
        payload = {}
        if target_date is not None:
            payload["target_date"] = target_date
        response = requests.post(
            self._get_url(endpoint),
            headers={**self.headers, "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        return response
