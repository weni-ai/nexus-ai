import requests
import json
import os

from typing import Dict


class SafeGuard:

    def __init__(self) -> None:
        self.url = os.environ.get("SAFEGUARD_URL")
        self.prompt = os.environ.get("SAFEGUARD_PROMPT")
        self.cookie = os.environ.get("SAFEGUARD_COOKIE")
        self.api_key = os.environ.get("SAFEGUARD_API_KEY")
        self.use_safeguard = os.environ.get("USE_SAFEGUARD")

    def request_safe_guard(self, formated_prompt: str):
        payload = json.dumps({
            "input": {
                "prompt": formated_prompt,
                "sampling_params": {
                    "max_tokens": 1024,
                    "top_p": 0.2,
                    "temperature": 0.1,
                    "stop": [
                        "<|end_of_text|>",
                        "<|eot_id|>"
                    ]
                }
            }
        })
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': self.api_key,
            'Cookie': self.cookie
        }

        return requests.request("POST", self.url, headers=headers, data=payload)

    def replace_vars(self, prompt: str, replace_variables: Dict) -> str:
        for key in replace_variables.keys():
            replace_str = "{{" + key + "}}"
            prompt = prompt.replace(replace_str, replace_variables.get(key))
        return prompt

    def get_prompt(self, message: str):
        variable = {
            "question": message
        }

        return self.replace_vars(self.prompt, variable)

    def classify(self, message: str):
        if self.use_safeguard == "false":
            return True

        formated_prompt = self.get_prompt(message)
        response = self.request_safe_guard(formated_prompt)
        safety_check = response.json()['output'][0]['choices'][0]['tokens'][0]
        if safety_check == "safe":
            return True
        return False
