import requests

from django.conf import settings

from nexus.internals import RestClient


class BillingRESTClient(RestClient):
    def __init__(self):
        self.base_url = settings.BILLING_REST_ENDPOINT

    def get_billing_active_contacts(
        self,
        user_token: str,
        project_uuid: str,
        start_date: str,
        end_date: str,
        page: int,
        search: str = None,
    ):

        # Build query parameters
        params = {
            "start": start_date,
            "end": end_date,
            "page": page,
        }

        # Add search parameter if provided
        if search:
            params["search"] = search

        # Build query string
        query_string = "&".join([f"{key}={value}" for key, value in params.items()])

        response = requests.get(
            f"{self.base_url}/api/v1/{project_uuid}/conversations/?{query_string}",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {user_token}",
            },
        )

        if response.status_code == 404:
            return {
                "count": 0,
                "next": None,
                "previous": None,
                "results": []
            }

        response.raise_for_status()
        return response.json()
