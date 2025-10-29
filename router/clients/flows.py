import json
import os
from typing import Dict

import requests

from router.entities import FlowDTO
from router.main import Message


class FlowClient:
    def __init__(self) -> None:
        self.base_url = os.environ.get("FLOWS_REST_ENDPOINT")
        self.token = os.environ.get("FLOWS_TOKEN")
        self.headers = {"Content-Type": "application/json"}

    def flows_start(
        self,
        flow: FlowDTO,
        message: Message,
        params: Dict,
        restart_participants: bool = True,
        exclude_active: bool = True,
    ):
        url = f"{self.base_url}/api/v2/flow_starts.json?token={self.token}"
        payload = json.dumps(
            {
                "flow": flow.uuid,
                "urns": [
                    f"whatsapp:{message.contact_urn}",
                ],
                "params": params,
                "restart_participants": restart_participants,
                "exclude_active": exclude_active,
            }
        )
        response = requests.post(url, headers=self.headers, data=payload)
        response.raise_for_status()
        return response.json()
