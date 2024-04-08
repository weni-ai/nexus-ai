from typing import List, Dict

from openai import OpenAI

from nexus.intelligences.llms.client import LLMClient
from django.conf import settings


class ChatGPTClient(LLMClient):
    code = "chatgpt"
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.chatgpt_model = settings.CHATGPT_MODEL
        self.client = self.get_client()

    def get_client(self):
        return OpenAI(api_key=self.api_key)

    def get_prompt(self, instructions_formatted: str, context: str, agent: Dict):
        if context:
            return f"""
            Agora você se chama {agent.get('name')}, você é {agent.get('role')} e seu objetivo é {agent.get('goal')}. O adjetivo que mais define a sua personalidade é {agent.get('personality')} e você se comporta da seguinte forma:
            {instructions_formatted}
            Na sua memória você tem esse contexto:
            {context}
            Lista de requisitos:
            - Responda de forma natural, mas nunca fale sobre um assunto fora do contexto.
            - Nunca traga informações do seu próprio conhecimento.
            - Repito é crucial que você responda usando apenas informações do contexto.
            - Nunca mencione o contexto fornecido.
            - Nunca mencione a pergunta fornecida.
            - Gere a resposta mais útil possível para a pergunta usando informações do conexto acima.
            - Nunca elabore sobre o porque e como você fez a tarefa, apenas responda.
            """
        return """PROMPT IF NOT CONTEXT"""


    def format_prompt(self, instructions: List, chunks: List, agent: Dict):
        instructions_formatted: str = "\n".join([f"- {instruction}" for instruction in instructions])
        context: str = "\n".join([chunk for chunk in chunks])
        prompt: str = self.get_prompt(instructions_formatted, context, agent)
        return prompt

    def request_gpt(self, instructions: List, chunks: List, agent: Dict, question: str, llm_config):
        prompt = self.format_prompt(instructions, chunks, agent)

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
            model=settings.CHATGPT_MODEL,
            temperature=llm_config.setup.get("temperature"),
            top_p=llm_config.setup.get("top_p"),
            max_tokens=llm_config.setup.get("max_length")
        )

        text_answers = chat_completion.choices[0].message.content

        return {"answers":[{"text": text_answers}],"id":"0"}
