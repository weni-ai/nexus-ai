from typing import List

from router.flow_start import FlowStart

from router.entities import FlowDTO


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
        llm_response: str = None,
        attachments: list = None,
    ) -> None:
        params = {
            "message": user_message,
        }

        if llm_response:
            params.update({"answer": llm_response})

        if attachments:
            params.update({"attachments": attachments})

        return {"type": "flowstart", "uuid": flow.uuid, "name": flow.name, "msg_event": msg_event, "params": params}
