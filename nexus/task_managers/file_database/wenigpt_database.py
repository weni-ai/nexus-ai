import json
import requests

from django.conf import settings
from typing import List
from nexus.usecases.task_managers.wenigpt_database import get_prompt_by_language

class WeniGPTDatabase:

    def __init__(self):
        self.url = settings.WENIGPT_API_URL
        self.token = settings.WENIGPT_API_TOKEN
        self.cookie = settings.WENIGPT_COOKIE

    def format_output(self, text_answers):
        answers = []
        if text_answers:
            for answer in text_answers:
                answer = answer.strip()
                ans = ""
                for ch in answer:
                    if ch == '\n':
                        break
                    ans += ch
                answers.append({"text": ans})
        return answers


    def request_wenigpt(self, contexts: List, question: str, language: str):
        context = "\n".join([str(ctx) for ctx in contexts])
        # base_prompt = f"{settings.WENIGPT_PROMPT_INTRODUCTION}{settings.WENIGPT_PROMPT_TEXT}{context}{settings.WENIGPT_PROMPT_QUESTION}{question}{settings.WENIGPT_PROMPT_REINFORCEMENT_INSTRUCTION}{settings.WENIGPT_PROMPT_ANSWER}"
        base_prompt = get_prompt_by_language(language=language, context=context, question=question)
        print(base_prompt)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Cookie": self.cookie
        }
        data = {
            "input": {
                "prompt": base_prompt,
                "sampling_params": {
                    "max_new_tokens": settings.WENIGPT_MAX_NEW_TOKENS,
                    "max_length": settings.WENIGPT_MAX_LENGHT,
                    "top_p": settings.WENIGPT_TOP_P,
                    "top_k": settings.WENIGPT_TOP_K,
                    "temperature": settings.WENIGPT_TEMPERATURE,
                    "do_sample": False,
                    "stop": settings.WENIGPT_STOP,
                }
            }
        }

        text_answers = None
        try:
            response = requests.request("POST", self.url, headers=headers, data=json.dumps(data))
            response_json = response.json()
            text_answers = response_json["output"].get("text")
        except Exception as e:
            response = {"error": str(e)}

        return {"answers": self.format_output(text_answers), "id": "0"}
