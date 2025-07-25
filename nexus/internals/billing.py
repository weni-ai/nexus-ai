import requests
from datetime import datetime

from django.conf import settings

from nexus.internals import RestClient


class BillingRESTClient(RestClient):
    def __init__(self):
        self.base_url = settings.BILLING_REST_ENDPOINT

    def _format_date_for_billing(self, date_str: str) -> str:
        """Convert date from YYYY-MM-DD to DD-MM-YYYY format for billing service"""
        try:
            # Parse the date in YYYY-MM-DD format
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            # Return in DD-MM-YYYY format
            return date_obj.strftime('%d-%m-%Y')
        except ValueError:
            # If parsing fails, return the original string
            return date_str

    def get_billing_active_contacts(
        self,
        user_token: str,
        project_uuid: str,
        start_date: str,
        end_date: str,
        page: int,
    ):
        # example: /<project_uuid>/conversations/?page=1&start=27-06-2025&end=04-07-2025

        # Format dates for billing service (DD-MM-YYYY)
        formatted_start_date = self._format_date_for_billing(start_date)
        formatted_end_date = self._format_date_for_billing(end_date)

        response = requests.get(
            f"{self.base_url}/{project_uuid}/conversations/?start={formatted_start_date}&end={formatted_end_date}&page={page}",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {user_token}",
            },
        )

        # Only handle 404 responses gracefully, let other errors propagate
        if response.status_code == 404:
            return {
                "count": 0,
                "next": None,
                "previous": None,
                "results": []
            }

        # For all other responses, raise for status to let Sentry handle them
        response.raise_for_status()
        return response.json()
