from typing import List, Dict

from openai import OpenAI

from nexus.intelligences.llms.client import LLMClient
from django.conf import settings

from router.entities.intelligences import LLMSetupDTO


class ChatGPTClient(LLMClient):
    code = "chatgpt"
    def __init__(
            self,
            api_key: str = None,
            chatgpt_model: str = settings.CHATGPT_MODEL,
            prompt_with_context: str = settings.CHATGPT_CONTEXT_PROMPT,
            prompt_without_context: str = settings.CHATGPT_NO_CONTEXT_PROMPT
            ):

        self.api_key = api_key
        self.chatgpt_model = chatgpt_model
        self.client = self.get_client()
        self.prompt_with_context = prompt_with_context
        self.prompt_without_context = prompt_without_context

    def get_client(self):
        return OpenAI(api_key=self.api_key)

    def format_prompt(self, instructions: List, chunks: List, agent: Dict):
        instructions_formatted: str = "\n".join([f"- {instruction}" for instruction in instructions])
        context: str = "\n".join([chunk for chunk in chunks])
        prompt: str = self.get_prompt(instructions_formatted, context, agent)
        return prompt

    def request_gpt(self, instructions: List, chunks: List, agent: Dict, question: str, llm_config: LLMSetupDTO):
        prompt = self.format_prompt(instructions, chunks, agent)

        print(f"[+ prompt enviado ao ChatGPT: {prompt} +]")

        kwargs = dict(
            temperature=float(llm_config.temperature),
            top_p=float(llm_config.top_p),
            max_tokens=int(llm_config.max_tokens) if llm_config.max_tokens else None
        )

        print(f"[+ Parametros enviados para o ChatGPT: {kwargs} +]")

        chat_completion = self.client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": prompt
                },
                {
                    "role": "user",
                    "content": question,
                }
            ],
            model=llm_config.model_version,
            **{k: v for k, v in kwargs.items() if v is not None}
        )

        text_answers = chat_completion.choices[0].message.content

        print(f"[+ Resposta do ChatGPT: {text_answers} +]")

        return {"answers":[{"text": text_answers}],"id":"0"}
