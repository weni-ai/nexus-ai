import requests
import json

from django.db import models
from django.conf import settings

from nexus.intelligences.models import ContentBase


class Flow(models.Model):
    uuid = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=255)
    prompt = models.TextField()
    fallback = models.BooleanField(default=False)
    content_base = models.ForeignKey(ContentBase, on_delete=models.CASCADE, related_name="flows")

    def generate_prompt(chatbot_goal, context):
        return f"""
            A partir dos dados fornecidos, gere um nome de classe que melhor represente o Contexto da classe passado e os requisitos informados.
            # Contexto da classe: {context}
            # Requisitos: 
            - O contexto da classe faz parte desse objetivo de chatbot: {chatbot_goal}
            - Responda sempre no formato: ```json\n{{\"class\": \"Nome da Classe\"}}\n```
            - O nome da classe pode ser composto e ter espaços, mas deve ser curto.
            """

    def generate_action_name(self, chatbot_goal, context):

        # One shot examples:
        one_shot_context = "Quando o usuário desejar APENAS consultar informações sobre o seu pedido."
        one_shot_chatbot_goal = "Atendimento ao cliente da Weni, com foco em tirar dúvidas sobre o processo de compra, políticas de troca e devolução."

        brain_goal = chatbot_goal
        brain_context = context

        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = json.dumps({
            "messages": [
                {
                    "role": "user",
                    "content": self.generate_prompt(
                        chatbot_goal=one_shot_chatbot_goal,
                        context=one_shot_context
                    )
                },
                {
                    "role": "assistant",
                    "content": "```json\n{\"class\": \"Consultar Pedido\"}\n```"
                },
                {
                    "role": "user",
                    "content": self.generate_prompt(
                        chatbot_goal=brain_goal,
                        context=brain_context
                    )
                }
            ],
            "model": settings.ACTION_GENERATE_NAME_MODEL,
            "response_format": {
                "type": "json_object"
            }
        })

        headers = {
            'Authorization': settings.ACTION_GENERATE_NAME_MODEL_AUTHORIZATION,
            'Content-Type': 'application/json'
        }
        # TODO - Add error handling, API and TestCase
        response = requests.request("POST", url, headers=headers, data=payload)
        return response.json()
