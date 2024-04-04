from typing import List

import requests

from router.direct_message import DirectMessage, exceptions


class BroadcastHTTPClient(DirectMessage):

    def __init__(self, host: str, access_token: str) -> None:
        self.__host = host
        self.__access_token = access_token

    def send_direct_message(self, text: str, urns: List, project_uuid: str, user: str) -> None:
        url = f"{self.__host}/api/v2/internals/broadcasts/"

        payload = {"user": user, "project": project_uuid, "urns": urns, "text": text}
        params = {"token": self.__access_token}

        response = requests.post(url, data=payload, params=params)

        try:
            response.raise_for_status()
        except Exception as error:
            raise exceptions.UnableToSendMessage(str(error))
