import json
import requests

from django.conf import settings

from dataclasses import dataclass

from nexus.actions.models import Flow, TemplateAction

from nexus.usecases.intelligences.get_by_uuid import (
    get_default_content_base_by_project,
)


@dataclass
class CreateFlowDTO:
    project_uuid: str
    flow_uuid: str
    name: str
    action_type: str = "custom"
    prompt: str = None
    fallback: bool = False
    action_template_uuid: str = None


class CreateFlowsUseCase():
    def create_flow(self, create_dto: CreateFlowDTO) -> Flow:

        if create_dto.action_type == "custom" and create_dto.prompt is None:
            raise ValueError("Prompt is required for custom actions")

        content_base = get_default_content_base_by_project(create_dto.project_uuid)

        if create_dto.action_template_uuid:
            action_template = TemplateAction.objects.get(uuid=create_dto.action_template_uuid)
            return Flow.objects.create(
                uuid=create_dto.flow_uuid,
                name=create_dto.name,
                prompt=create_dto.prompt,
                fallback=create_dto.fallback,
                content_base=content_base,
                action_type=create_dto.action_type,
                action_template=action_template
            )

        return Flow.objects.create(
            uuid=create_dto.flow_uuid,
            name=create_dto.name,
            prompt=create_dto.prompt,
            fallback=create_dto.fallback,
            content_base=content_base,
            action_type=create_dto.action_type,
        )


class CreateTemplateActionUseCase():

    def create_template_action(
        self,
        name: str,
        prompt: str,
        action_type: str,
        display_prompt: str = None,
        group: str = None
    ):
        try:
            if display_prompt is None:
                display_prompt = prompt

            return TemplateAction.objects.create(
                name=name,
                prompt=prompt,
                action_type=action_type,
                group=group,
                display_prompt=display_prompt
            )
        except Exception as e:
            print("error", str(e))
            raise Exception("Error creating template action")


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
            - Gere a classe no mesmo idioma do contexto.
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
