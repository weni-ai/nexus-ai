import json
from typing import List, Dict

import requests

from django.conf import settings

from nexus.intelligences.llms.client import LLMClient
from router.entities import LLMSetupDTO


class WeniGPTClient(LLMClient):
    code = "wenigpt"

    def __init__(self, model_version: str):
        self.url = settings.WENIGPT_API_URL
        self.token = settings.WENIGPT_API_TOKEN
        self.cookie = settings.WENIGPT_COOKIE
        self.api_key = settings.WENIGPT_OPENAI_TOKEN

        self.model_version = model_version

        self.prompt_with_context = settings.WENIGPT_CONTEXT_PROMPT
        self.prompt_without_context = settings.WENIGPT_NO_CONTEXT_PROMPT

        self.fine_tunning_models = settings.WENIGPT_FINE_TUNNING_VERSIONS

        self.fine_tunning_prompt_with_context = settings.CHATGPT_CONTEXT_PROMPT
        self.fine_tunning_prompt_without_context = settings.CHATGPT_NO_CONTEXT_PROMPT

        self.post_prompt = settings.WENIGPT_POST_PROMPT

        self.headers = self._get_headers()

    def _get_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Cookie": self.cookie
        }

    def format_prompt(self, instructions: List, chunks: List, agent: Dict, question: str = None) -> str:
        instructions_formatted = "\n".join([f"- {instruction}" for instruction in instructions])
        context = "\n".join([chunk for chunk in chunks])
        prompt = self.get_prompt(instructions_formatted, context, agent, question)
        return prompt.replace("\\n", "\n")

    def request_runpod(self, instructions: List, chunks: List, agent: Dict, question: str, llm_config: LLMSetupDTO):
        self.prompt = self.format_prompt(instructions, chunks, agent, question)
        data = {
            "input": {
                "prompt": self.prompt,
                "sampling_params": {
                    "max_tokens": int(llm_config.max_length) if isinstance(llm_config.max_length, int) else int(settings.WENIGPT_MAX_LENGHT),
                    "top_p": float(llm_config.top_p),
                    "top_k": float(llm_config.top_k),
                    "temperature": float(llm_config.temperature),
                    "stop": settings.WENIGPT_STOP,
                }
            }
        }

        text_answers = None

        try:
            print(f"Request para o Wenigpt: {self.prompt}")
            response = requests.request("POST", self.url, headers=self.headers, data=json.dumps(data))
            response_json = response.json()
            print(f"Resposta Json do WeniGPT: {response_json}")
            text_answers = response_json["output"][0].get("choices")[0].get("tokens")[0]

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
                "answers": [
                    {
                        "text": text_answers
                    }
                ],
                "id": "0",
                # "question_uuid": str(log.user_question.uuid)
            }

        except Exception as e:
            response = {"error": str(e)}
            return {"answers": None, "id": "0", "message": response.get("error")}

    def request_gpt(self, instructions: List, chunks: List, agent: Dict, question: str, llm_config: LLMSetupDTO):

        if self.model_version in self.fine_tunning_models:
            self.client = self.get_client()

            self.prompt_with_context = self.fine_tunning_prompt_with_context
            self.prompt_without_context = self.fine_tunning_prompt_without_context

            return self.chat_completion(instructions, chunks, agent, question, llm_config)

        return self.request_runpod(instructions, chunks, agent, question, llm_config)
