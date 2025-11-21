import json
from typing import List

import requests

from router.entities.flow import FlowDTO
from router.flow_start import FlowStart, exceptions


class FlowStartHTTPClient(FlowStart):
    def __init__(self, host: str, access_token: str) -> None:
        self.__host = host
        self.__access_token = access_token

    def start_flow(
        self,
        flow: FlowDTO,
        user: str,
        urns: List,
        user_message: str,
        msg_event: dict = None,
        attachments: list = None,
        llm_response: str = None,
    ) -> None:
        url = f"{self.__host}/api/v2/internals/flow_starts/"

        payload = {
            "user": user,
            "flow": flow.uuid,
            "urns": urns,
            "params": {
                "message": user_message,
            },
        }

        if msg_event:
            payload["params"]["msg_event"] = msg_event

        if attachments:
            payload["params"]["attachments"] = attachments

        if llm_response:
            payload["params"]["answer"] = llm_response

        params = {"token": self.__access_token}
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, data=json.dumps(payload), params=params, headers=headers)

        try:
            response.raise_for_status()
        except Exception as error:
            raise exceptions.UnableToStartFlow(str(error)) from error
