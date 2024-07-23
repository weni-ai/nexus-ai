import requests
import json

from django.db import models

from nexus.intelligences.models import ContentBase


class Flow(models.Model):
    uuid = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=255)
    prompt = models.TextField()
    fallback = models.BooleanField(default=False)
    content_base = models.ForeignKey(ContentBase, on_delete=models.CASCADE, related_name="flows")

    def name_generator(
        self,
        prompt:str,
        goal:str
    ):
        # Contexto da classe: {context}

        # Requisitos: 
        instruction = []
        instruction.append(f"O contexto da classe faz parte desse objetivo de chatbot: {goal}")
        instruction.append("Responda sempre no formato: ```json\n{{\"class\": \"Nome da Classe\"}}\n```")
        instruction.append("O nome da classe pode ser composto e ter espaços, mas deve ser curto.")

        payload = json.dumps({
            "messages": [
                {
                    "role": "user",
                    "content": generate_prompt(one_shot_chatbot_goal, one_shot_context)
                },
                {
                    "role": "assistant",
                    "content": "```json\n{\"class\": \"Consultar Pedido\"}\n```"
                },
                {
                    "role": "user",
                    "content": generate_prompt(chatbot_goal, context)
                }
            ],
            "model": "llama3-70b-8192",
            "response_format": {
                "type": "json_object"
            }
        })

        headers = {
        'Authorization': 'Bearer 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',
        'Content-Type': 'application/json'
        }

        response = requests.request("POST", url, headers=headers, data=payload)
        return response.json()