from typing import List

import requests

from router.flow_start import FlowStart, exceptions


class FlowStartHTTPClient(FlowStart):

    def __init__(self, host: str, access_token: str) -> None:
        self.__host = host
        self.__access_token = access_token

    def start_flow(self, flow: str, user: str, urns: List) -> None:
        print("================================")
        print(f"ta chamando o fluxo {flow} para {urns}")
        print("================================")
        url = f"{self.__host}/api/v2/internals/flow_starts/"

        payload = {"user": user, "flow": flow, "urns": urns}

        params = {"token": self.__access_token}

        response = requests.post(url, data=payload, params=params)

        print("==========Resposta do flows ======================")
        print(f"{response}")
        print("================================")

        try:
            response.raise_for_status()
        except Exception as error:
            raise exceptions.UnableToStartFlow(str(error))
