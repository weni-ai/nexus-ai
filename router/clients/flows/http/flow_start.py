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
        msg_event: dict = None
    ) -> None:

        url = f"{self.__host}/api/v2/internals/flow_starts/"

        payload = {
            "user": user,
            "flow": flow.uuid,
            "urns": urns,
            "params": {
                "message": user_message,
            }
        }

        if msg_event:
            payload["params"]["msg_event"] = msg_event

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
