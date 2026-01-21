import logging
from typing import Dict, List

import requests
from django.conf import settings

from nexus.internals import InternalAuthentication, RestClient
from nexus.usecases.jwt.jwt_usecase import JWTUsecase

logger = logging.getLogger(__name__)


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
        params = {"project": project_uuid, "page_size": page_size, "page": page}
        try:
            response = requests.get(
                self._get_url("/api/v2/internals/flows"), headers=self.authentication_instance.headers, params=params
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            return {"count": 0, "next": None, "previous": None, "results": []}

    def get_project_flows(self, project_uuid: str, flow_name: str):
        try:
            params = dict(flow_name=flow_name, project=project_uuid)
            response = requests.get(
                url=self._get_url("/api/v2/internals/project-flows/"),
                headers=self.authentication_instance.headers,
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            return []

    def list_project_contact_fields(self, project_uuid: str):
        try:
            params = dict(project=project_uuid)

            response = requests.get(
                url=self._get_url("/api/v2/internals/contacts_fields"),
                headers=self.authentication_instance.headers,
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            return []

    def create_project_contact_field(self, project_uuid: str, key: str, value_type: str):
        try:
            body = dict(project=project_uuid, label=key, value_type=value_type)

            response = requests.post(
                url=self._get_url("/api/v2/internals/contacts_fields"),
                headers=self.authentication_instance.headers,
                json=body,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            return {}

    def whatsapp_broadcast(
        self, urns: List[str], msg: Dict, project_uuid: str, use_stream: bool = False, channel_uuid: str = ""
    ):
        if use_stream:
            url = self._get_url("/api/v2/internals/messages/stream")
        else:
            url = self._get_url("/api/v2/internals/whatsapp_broadcasts")

        body = dict(urns=urns, project=project_uuid)
        if use_stream and channel_uuid:
            body["channel_uuid"] = channel_uuid
        body.update(msg)

        jwt_usecase = JWTUsecase()
        jwt_token = jwt_usecase.generate_broadcast_jwt_token()
        headers = {"Content-Type": "application/json; charset: utf-8", "Authorization": f"Bearer {jwt_token}"}

        logger.info(
            f"[Broadcast] Sending request - url: {url}, use_stream: {use_stream}, "
            f"project: {project_uuid}, urns: {urns}, body: {body}"
        )

        response = requests.post(url, json=body, headers=headers)

        logger.info(
            f"[Broadcast] Response received - url: {url}, use_stream: {use_stream}, "
            f"status_code: {response.status_code}, project: {project_uuid}"
        )
        return response
