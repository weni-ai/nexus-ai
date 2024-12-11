import json
import requests

from typing import List

from router.flow_start import FlowStart, exceptions
from router.entities.flow import FlowDTO


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
        llm_message: str = None,
        msg_event: dict = None,
        attachments: list = None
    ) -> None:

        url = f"{self.__host}/api/v2/internals/flow_starts/"
        params = {
            "message": user_message,
        }

        if llm_message:
            params.update({"answer": llm_message})

        payload = {
            "user": user,
            "flow": flow.uuid,
            "urns": urns,
            "params": params
        }

        if msg_event:
            payload["params"]["msg_event"] = msg_event

        if attachments:
            payload["params"]["attachments"] = attachments

        params = {
            "token": self.__access_token
        }
        headers = {
            'Content-Type': 'application/json'
        }
        response = requests.post(url, data=json.dumps(payload), params=params, headers=headers)

        try:
            response.raise_for_status()
        except Exception as error:
            raise exceptions.UnableToStartFlow(str(error))
