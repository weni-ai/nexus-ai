import logging
from typing import List

import requests

from router.direct_message import DirectMessage, exceptions

logger = logging.getLogger(__name__)


class BroadcastHTTPClient(DirectMessage):
    def __init__(self, host: str, access_token: str) -> None:
        self.__host = host
        self.__access_token = access_token

    def send_direct_message(self, text: str, urns: List, project_uuid: str, user: str, **kwargs) -> None:
        url = f"{self.__host}/api/v2/internals/broadcasts/"

        payload = {"user": user, "project": project_uuid, "urns": urns, "text": text}
        params = {"token": self.__access_token}

        logger.debug("Broadcast payload", extra={"payload_keys": list(payload.keys())})

        response = requests.post(url, data=payload, params=params)
        logger.debug("Broadcast response", extra={"text_len": len(response.text or "")})
        try:
            response.raise_for_status()
        except Exception as error:
            raise exceptions.UnableToSendMessage(str(error)) from error
