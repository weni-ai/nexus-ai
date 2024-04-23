from typing import List, Dict

from router.flow_start import FlowStart

from router.entities import FlowDTO


class SimulateFlowStart(FlowStart):
    def __init__(self, host: str, access_token: str) -> None:
        self.__host = host
        self.__access_token = access_token

    def start_flow(self, flow: FlowDTO, user: str, urns: List) -> None:
        return {"type": "flowstart", "uuid": flow.uuid, "name": flow.name}
