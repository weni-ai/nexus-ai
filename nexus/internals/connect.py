import logging

import requests
from django.conf import settings

from nexus.internals import InternalAuthentication, RestClient

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en-us"


class ConnectRESTClient(RestClient):
    def __init__(self):
        self.base_url = settings.CONNECT_REST_ENDPOINT
        self.authentication_instance = InternalAuthentication()

    def _get_url(self, endpoint: str) -> str:
        assert endpoint.startswith("/"), "the endpoint needs to start with: /"
        return self.base_url + endpoint

    def get_project_language(self, project_uuid: str) -> str:
        try:
            response = self.authentication_instance.make_request_with_retry(
                "GET",
                self._get_url(f"/v2/internals/connect/projects/{project_uuid}"),
                timeout=10,
            )
            response.raise_for_status()
            return response.json().get("language", DEFAULT_LANGUAGE)
        except (requests.exceptions.RequestException, ValueError, KeyError) as exc:
            logger.warning(
                "Failed to fetch project language from Connect API for project %s: %s",
                project_uuid,
                exc,
            )
            return DEFAULT_LANGUAGE
