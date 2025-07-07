import requests

from django.conf import settings

from nexus.internals import RestClient, InternalAuthentication


class BillingRESTClient(RestClient):
    def __init__(self):
        self.base_url = settings.BILLING_REST_ENDPOINT
        self.authentication_instance = InternalAuthentication()

    def _get_url(self, endpoint: str) -> str:
        assert endpoint.startswith("/"), "the endpoint needs to start with: /"
        return self.base_url + endpoint

    def get_billing_active_contacts(
        self,
        project_uuid: str,
        start_date: str,
        end_date: str,
        page: int,
    ):
        # example: /<project_uuid>/conversations/?page=1&start=27-06-2025&end=04-07-2025

        response = requests.get(
            self._get_url(f"/{project_uuid}/conversations/?start={start_date}&end={end_date}&page={page}"),
            headers=self.authentication_instance.headers,
        )
        return response.json()
