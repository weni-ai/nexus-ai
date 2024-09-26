import requests
import json
import os


class PromptGuard:

    def __init__(self) -> None:
        self.url = os.environ.get("PROMPT_GUARD_URL")
        self.api_key = os.environ.get("PROMPT_GUARD_API_KEY")
        self.use_prompt_guard = os.environ.get("USE_PROMPT_GUARD")

    def request_safe_guard(self, user_message: str):
        payload = json.dumps(
            {
                "input": {
                    "text": user_message
                }
            }
        )
        headers = {
            'Authorization': self.api_key,
        }

        return requests.request("POST", self.url, headers=headers, data=payload)

    def classify(self, message: str):
        if self.use_prompt_guard == "false":
            return True

        response = self.request_safe_guard(message)
        classification = response.json()['output']['guardrails_classification']
        if classification.lower() == "injection":
            return False
        return True
