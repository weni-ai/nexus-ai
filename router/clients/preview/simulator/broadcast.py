from typing import List, Dict

from router.direct_message import DirectMessage


class SimulateBroadcast(DirectMessage):
    def __init__(self, host: str, access_token: str) -> None:
        self.__host = host
        self.__access_token = access_token

    def send_direct_message(self, text: str, urns: List, project_uuid: str, user: str) -> None:
        return {"type": "broadcast", "message": text}
