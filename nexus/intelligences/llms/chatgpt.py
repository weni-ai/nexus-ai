from typing import List, Dict

from openai import OpenAI

from nexus.intelligences.llms.client import LLMClient
from django.conf import settings


class ChatGPTClient(LLMClient):
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.chatgpt_model = settings.CHATGPT_MODEL
        self.client = self.get_client()

    def get_client(self):
        return OpenAI(api_key=self.api_key)

    def format_prompt(self, instructions: List, chunks: List, agent: Dict):
        instructions_formatted = "\n".join([f"- {instruction}" for instruction in instructions])
        context = "\n".join([chunk for chunk in chunks])
        prompt = f"""
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
        return prompt

    def request_gpt(self, instructions: List, chunks: List, agent: Dict, question: str):
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
            model=settings.CHATGPT_MODEL
        )

        text_answers = chat_completion.choices[0].message.content

        return {"answers":[{"text": text_answers}],"id":"0"}
