from typing import List, Dict

import requests
import json

from nexus.internals.flows import FlowsRESTClient
from router.direct_message import DirectMessage, exceptions


class SendMessageHTTPClient(DirectMessage):

    def __init__(self, host: str, access_token: str) -> None:
        self.__host = host
        self.__access_token = access_token

    def send_direct_message(self, text: str, urns: List, project_uuid: str, user: str, full_chunks: List[Dict]) -> None:
        url = f"{self.__host}/mr/msg/send"

        payload = {"user": user, "project_uuid": project_uuid, "urns": urns, "text": text}
        headers = {
            "Authorization": f"Token {self.__access_token}",
            'Content-Type': 'application/json'
        }

        payload = json.dumps(payload).encode("utf-8")

        response = requests.post(url, data=payload, headers=headers)
        print("Resposta: ", response.text)
        try:
            response.raise_for_status()
        except Exception as error:
            raise exceptions.UnableToSendMessage(str(error))



class WhatsAppBroadcastHTTPClient(DirectMessage):

    def __init__(self, host: str, access_token: str) -> None:
        self.__host = host
        self.__access_token = access_token

    def send_direct_message(
        self, 
        msg: Dict, 
        urns: List,
    ) -> None:
        response = FlowsRESTClient().whatsapp_broadcast(urns, msg)
        try:
            response.raise_for_status()
        except Exception as error:
            raise exceptions.UnableToSendMessage(str(error))
