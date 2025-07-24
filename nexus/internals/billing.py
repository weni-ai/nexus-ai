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
        # example: /<project_uuid>/conversations/?page=1&start=27-06-2025&end=04-07-2025

        response = requests.get(
            f"{self.base_url}/{project_uuid}/conversations/?start={start_date}&end={end_date}&page={page}",
            headers={
                "Content-Type": "application/json; charset: utf-8",
                "Authorization": f"Bearer {user_token}",
            },
        )
        return response.json()
