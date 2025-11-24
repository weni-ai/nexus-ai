import json
import logging
import os
from typing import Dict, List

import requests

from nexus.zeroshot.client import InvokeModel


class NexusZeroshotClient:
    def __init__(self, prompt: str) -> None:
        self.prompt = prompt

    def fast_predict(self, message: str, actions: List[Dict], language: str = "por"):
        logging.getLogger(__name__).info("Calling Zeroshot in Nexus")
        zeroshot_data = {"context": self.prompt, "language": language, "text": message, "options": actions}
        zeroshot = InvokeModel(zeroshot_data)
        response = zeroshot.invoke()
        return response.get("output")


class ZeroshotClient:
    def __init__(self, prompt: str) -> None:
        self.base_url = os.environ.get("ZEROSHOT_URL")
        self.prompt = prompt
        self.token = os.environ.get("BOTHUB_ZEROSHOT_TOKEN")

    def fast_predict(self, message: str, actions: List[Dict], language: str = "por"):
        url = f"{self.base_url}/v2/repository/nlp/zeroshot/zeroshot-fast-predict"

        payload = {"context": self.prompt, "language": language, "text": message, "options": actions}

        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

        response = requests.request("POST", url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        return response.json().get("output")
