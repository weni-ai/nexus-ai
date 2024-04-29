from typing import List, Dict

from nexus.intelligences.llms.client import LLMClient
from django.conf import settings

from router.entities import LLMSetupDTO, ContactMessageDTO


class ChatGPTClient(LLMClient):
    code = "chatgpt"

    def __init__(
            self,
            api_key: str = None,
            model_version: str = settings.CHATGPT_MODEL,
            prompt_with_context: str = settings.CHATGPT_CONTEXT_PROMPT,
            prompt_without_context: str = settings.CHATGPT_NO_CONTEXT_PROMPT
    ):

        self.api_key = api_key
        self.chatgpt_model = model_version
        self.client = self.get_client()

        self.prompt_with_context = prompt_with_context
        self.prompt_without_context = prompt_without_context

        self.few_shot = settings.FEW_SHOT_CHATGPT
        self.post_prompt = settings.CHATGPT_POST_PROMPT

    def format_prompt(self, instructions: List, chunks: List, agent: Dict):
        instructions_formatted = "\n".join([f"- {instruction}" for instruction in instructions])
        context: str = "\n".join([chunk for chunk in chunks])
        prompt: str = self.get_prompt(instructions_formatted, context, agent)
        return prompt

    def request_gpt(self, instructions: List, chunks: List, agent: Dict, question: str, llm_config: LLMSetupDTO, last_messages: List[ContactMessageDTO]):
        return self.chat_completion(
            instructions=instructions,
            chunks=chunks,
            agent=agent,
            question=question,
            llm_config=llm_config,
            few_shot=self.few_shot,
            last_messages=last_messages
        )
