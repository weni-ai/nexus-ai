import json
import requests

from django.conf import settings

from router.entities import LLMSetupDTO
from router.classifiers.interfaces import ModelVersionReflection


class WenigPTSharkReflection(ModelVersionReflection):
    def __init__(
        self,
        strategy=None
    ):
        self.strategy = strategy or self.basic_reflection_strategy

    def request_reflection(
        self,
        prompt: str,
        llm_config: LLMSetupDTO
    ) -> dict:

        url = settings.WENIGPT_SHARK_API_URL
        token = settings.WENIGPT_API_TOKEN
        cookies = settings.WENIGPT_COOKIE

        max_tokens = int(llm_config.max_length) if isinstance(llm_config.max_length, int) else int(settings.WENIGPT_MAX_LENGHT)
        sampling_params = {
            "max_tokens": max_tokens,
            "top_p": float(llm_config.top_p),
            "top_k": float(llm_config.top_k),
            "temperature": float(llm_config.temperature),
            "stop": settings.WENIGPT_STOP,
        }

        if settings.TOKEN_LIMIT:
            sampling_params["max_tokens"] = settings.TOKEN_LIMIT

        data = {
            "input": {
                "prompt": prompt,
                "sampling_params": sampling_params
            }
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "Cookie": cookies
        }

        response = requests.post(url, headers=headers, data=json.dumps(data))
        response_json = response.json()
        text_answers = response_json["output"][0]["choices"][0]["tokens"][0]

        return {
            "answers": [{"text": text_answers}],
            "id": "0",
        }

    def format_prompt(
        self,
        last_response: str,
        user_question: str,
        last_prompt: str,
        last_messages: list = []
    ) -> str:

        shark_reflection_prompt = settings.WENIGPT_SHARK_CONTEXT_PROMPT
        shark_reflection_prompt = shark_reflection_prompt.replace("{{system_prompt}}", last_prompt)
        shark_reflection_prompt = shark_reflection_prompt.replace("{{history}}", last_messages)
        shark_reflection_prompt = shark_reflection_prompt.replace("{{question}}", user_question)
        shark_reflection_prompt = shark_reflection_prompt.replace("{{llm_response}}", last_response)

        return shark_reflection_prompt

    def basic_reflection_strategy(
        self,
        prompt: str
    ) -> str:
        return prompt

    def reflect(
        self,
        message_to_reflect: str
    ) -> str:
        formated_prompt = self.format_prompt(message_to_reflect)
        return self.strategy(message_to_reflect)
