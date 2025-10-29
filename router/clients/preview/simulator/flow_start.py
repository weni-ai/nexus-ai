from typing import List

from router.entities import FlowDTO
from router.flow_start import FlowStart


class SimulateFlowStart(FlowStart):
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
        params = {
            "message": user_message,
        }
        if llm_response:
            params.update({"answer": llm_response})

        if attachments:
            params.update({"attachments": attachments})

        response_data = {
            "type": "flowstart",
            "uuid": flow.uuid,
            "name": flow.name,
            "msg_event": msg_event,
            "params": params,
        }

        return response_data
