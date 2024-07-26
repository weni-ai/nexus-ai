import json
import requests

from django.conf import settings

from dataclasses import dataclass

from nexus.actions.models import Flow

from nexus.usecases.intelligences.get_by_uuid import (
    get_default_content_base_by_project,
)


@dataclass
class CreateFlowDTO:
    project_uuid: str
    flow_uuid: str
    name: str
    prompt: str
    fallback: bool = False


class CreateFlowsUseCase():
    def create_flow(self, create_dto: CreateFlowDTO) -> Flow:

        content_base = get_default_content_base_by_project(create_dto.project_uuid)

        return Flow.objects.create(
            uuid=create_dto.flow_uuid,
            name=create_dto.name,
            prompt=create_dto.prompt,
            fallback=create_dto.fallback,
            content_base=content_base
        )


class GenerateFlowNameUseCase():

    def __init__(self, request_func=None):
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.headers = {
            'Authorization': settings.ACTION_GENERATE_NAME_MODEL_AUTHORIZATION,
            'Content-Type': 'application/json'
        }
        self.request_func = request_func or requests.request

    def request_action_name(self, payload):
        try:
            response = self.request_func(
                "POST",
                self.url,
                headers=self.headers,
                data=payload
            )

            response_json = response.json()["choices"][0]["message"]["content"]
            generated_name = json.loads(response_json)["class"]
            return {"action_name": generated_name}
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def generate_prompt(self, chatbot_goal, context):
        return f"""
            A partir dos dados fornecidos, gere um nome de classe que melhor represente o Contexto da classe passado e os requisitos informados.
            # Contexto da classe: {context}
            # Requisitos: 
            - O contexto da classe faz parte desse objetivo de chatbot: {chatbot_goal}
            - Responda sempre no formato: ```json\n{{\"class\": \"Nome da Classe\"}}\n```
            - O nome da classe pode ser composto e ter espaços, mas deve ser curto.
            """

    def generate_action_name(self, chatbot_goal, context):

        # Examples to help the model understand:
        one_shot_context = "Quando o usuário desejar APENAS consultar informações sobre o seu pedido."
        one_shot_chatbot_goal = "Atendimento ao cliente da Weni, com foco em tirar dúvidas sobre o processo de compra, políticas de troca e devolução."

        brain_goal = chatbot_goal
        brain_context = context

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

        return self.request_action_name(payload)
