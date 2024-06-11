from typing import List
from openai import OpenAI
from django.conf import settings

from nexus.task_managers.file_database import GPTDatabase

from nexus.intelligences.llms.chatgpt import ChatGPTClient
from router.entities.intelligences import LLMSetupDTO


class ChatGPTDatabase(GPTDatabase):

    language_codes = {
        "pt": "português",
        "en": "inglês",
        "es": "espanhol",
    }

    def __init__(self, api_key: str = settings.OPENAI_API_KEY):
        self.api_key = api_key
        self.chatgpt_model = settings.CHATGPT_MODEL
        self.client = ChatGPTClient(api_key=self.api_key)
        self.default_instructions = settings.DEFAULT_INSTRUCTIONS
        self.default_agent = dict(
            name=settings.DEFAULT_AGENT_NAME,
            role=settings.DEFAULT_AGENT_ROLE,
            goal=settings.DEFAULT_AGENT_GOAL,
            personality=settings.DEFAULT_AGENT_PERSONALITY
        )
        self.default_llm_config = LLMSetupDTO(model="chatgpt", model_version="gpt-4o", temperature=0.1, top_p=0.1, token=self.api_key)

    def get_client(self):
        return OpenAI(api_key=self.api_key)

    def request_gpt(
        self,
        contexts: List,
        question: str,
        language: str,
        content_base_uuid: str,
        testing: bool = False
    ):
        self.default_instructions.append(f"Responda sempre em {self.language_codes.get(language, 'português')}")

        gpt_response = self.client.request_gpt(
            self.default_instructions,
            contexts,
            self.default_agent,
            question,
            self.default_llm_config)

        text_answer = None
        text_answer = gpt_response.get("answers")[0].get("text")
        return {"answers": [{"text": text_answer}], "id": "0"}
