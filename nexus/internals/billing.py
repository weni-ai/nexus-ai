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
    ):

        response = requests.get(
            f"{self.base_url}/api/v1/{project_uuid}/conversations/?start={start_date}&end={end_date}&page={page}",
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
