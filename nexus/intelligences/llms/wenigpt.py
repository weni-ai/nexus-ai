import json
from typing import List, Dict

import requests

from django.conf import settings

from nexus.intelligences.llms.client import LLMClient
from nexus.task_managers.tasks import create_wenigpt_logs
from nexus.usecases.intelligences.intelligences_dto import ContentBaseLogsDTO
from router.entities import LLMSetupDTO

class WeniGPTClient(LLMClient):
    code = "wenigpt"
    def __init__(self):
        self.url = settings.WENIGPT_API_URL
        self.token = settings.WENIGPT_API_TOKEN
        self.cookie = settings.WENIGPT_COOKIE
        self.headers = self._get_headers()
        self.prompt_with_context = settings.WENIGPT_CONTEXT_PROMPT
        self.prompt_without_context = settings.WENIGPT_NO_CONTEXT_PROMPT

    def _get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Cookie": self.cookie
        }

    def format_prompt(self, instructions: List, chunks: List, agent: Dict, question: str) -> str:
        instructions_formatted = "\n".join([f"- {instruction}" for instruction in instructions])
        context = "\n".join([chunk for chunk in chunks])
        prompt = self.get_prompt(instructions_formatted, context, agent, question)
        return prompt

    def request_gpt(self, instructions: List, chunks: List, agent: Dict, question: str, llm_config: LLMSetupDTO):
        prompt = self.format_prompt(instructions, chunks, agent, question),
        data = {
            "input": {
                "prompt": prompt,
                "sampling_params": {
                    "max_tokens": llm_config.max_length,
                    "top_p": llm_config.top_p,
                    "top_k": llm_config.top_k,
                    "temperature": llm_config.temperature,
                    "stop": settings.WENIGPT_STOP,
                }
            }
        }

        text_answers = None

        try:
            response = requests.request("POST", self.url, headers=self.headers, data=json.dumps(data))
            response_json = response.json()
            print(f"Resposta Json do WeniGPT: {response_json}")
            text_answers = response_json["output"].get("text")

            # log_dto = ContentBaseLogsDTO(
            #     content_base_uuid=content_base_uuid,
            #     question=question,
            #     language=language,
            #     texts_chunks=contexts,
            #     full_prompt=base_prompt,
            #     weni_gpt_response=text_answers,
            #     testing=testing
            # )
            # log = create_wenigpt_logs(log_dto.__dict__)

            return {
                "answers": self.format_output(text_answers),
                "id": "0",
                # "question_uuid": str(log.user_question.uuid)
            }

        except Exception as e:
            response = {"error": str(e)}
            print(response)
            return {"answers": None, "id": "0", "message": response.get("error")}
