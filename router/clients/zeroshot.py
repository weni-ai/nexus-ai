import os
import json

from typing import List, Dict

import requests


class ZeroshotClient:
    def __init__(self) -> None:
        self.base_url = os.environ.get("ZEROSHOT_URL")
        self.prompt = os.environ.get("ZEROSHOT_PROMPT")
        self.token = os.environ.get("ZEROSHOT_TOKEN")
    
    def fast_predict(self, message: str, actions: List[Dict], language: str =" por"):
        url = f"{self.base_url}/v2/repository/nlp/zeroshot/zeroshot-fast-predict"

        payload = {
            "context": self.prompt,
            "language": language,
            "text": message,
            "options": actions
        }

        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }

        response = requests.request("POST", url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        return response.json().get("output")
