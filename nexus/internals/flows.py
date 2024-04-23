from django.conf import settings

import requests

from nexus.internals import InternalAuthentication, RestClient


class FlowsRESTClient(RestClient):

    def __init__(self):
        self.base_url = settings.FLOWS_REST_ENDPOINT
        self.authentication_instance = InternalAuthentication()

    def _get_url(self, endpoint: str) -> str:
        assert endpoint.startswith("/"), "the endpoint needs to start with: /"
        return self.base_url + endpoint

    def create_external_service(self, user: str, flow_organization: str, type_fields: dict, type_code: str):
        body = dict(user=user, org=flow_organization, type_fields=type_fields, type_code=type_code)

        return requests.post(
            self._get_url("/api/v2/internals/externals"),
            headers=self.authentication_instance.headers,
            json=body,
        )

    def list_project_flows(self, project_uuid: str, page_size: int = None, page: int = None):
        params = {
            "project": project_uuid,
            "page_size": page_size,
            "page": page
        }
        try:
            response = requests.get(
                self._get_url("/api/v2/internals/flows"),
                headers=self.authentication_instance.headers,
                params=params
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            return {'count': 0, 'next': None, 'previous': None, 'results': []}

    def get_project_flows(self, project_uuid: str, flow_name: str):
        try:
            params = dict(
                flow_name=flow_name,
                project=project_uuid
            )
            response = requests.get(
                url=self._get_url("/api/v2/internals/project-flows/"),
                headers=self.authentication_instance.headers,
                params=params
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            return []
