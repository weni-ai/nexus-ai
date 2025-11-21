import json
import os
from typing import Any

import boto3
from agents import (
    Agent,
    AgentHooks,
    ModelSettings,
    RunContextWrapper,
    function_tool,
)
from django.conf import settings
from openai.types.shared import Reasoning

from inline_agents.backends.openai.entities import Context
from nexus.utils import get_datasource_id
from router.clients.flows.http.send_message import WhatsAppBroadcastHTTPClient


class Supervisor(Agent):
    def function_tools(self, audio_orchestration: bool = False, exclude_tools_from_audio_orchestration: list[str] = [], exclude_tools_from_text_orchestration: list[str] = []) -> list:
        tools = [self.send_message_with_url_button, self.knowledge_base_bedrock]
        if audio_orchestration:
            tools = [tool for tool in tools if tool.name not in exclude_tools_from_audio_orchestration]
        else:
            tools = [tool for tool in tools if tool.name not in exclude_tools_from_text_orchestration]
        return tools

    def __init__(
        self,
        name: str,
        instructions: str,
        model: str,
        tools: list[Any],
        hooks: list[AgentHooks] | None = None,
        handoffs: list[Agent] | None = None,
        prompt_override_configuration: dict | None = None,
        preview: bool = False,
        max_tokens: int | None = None,
        use_components: bool = False,
        **kwargs
    ):
        exclude_tools_from_audio_orchestration = kwargs.get("exclude_tools_from_audio_orchestration", [])
        exclude_tools_from_text_orchestration = kwargs.get("exclude_tools_from_text_orchestration", [])
        tools.extend(self.function_tools(audio_orchestration=kwargs.get("audio_orchestration", False), exclude_tools_from_audio_orchestration=exclude_tools_from_audio_orchestration, exclude_tools_from_text_orchestration=exclude_tools_from_text_orchestration))
        if model in settings.MODELS_WITH_REASONING:
            super().__init__(
                name=name,
                instructions=instructions,
                model=model,
                tools=tools,
                hooks=hooks,
                model_settings=ModelSettings(
                    max_tokens=max_tokens,
                    reasoning=Reasoning(
                        effort="medium",
                        summary="auto"
                    ),
                )
            )
            return

        if use_components:
            super().__init__(
                name=name,
                instructions=instructions,
                model=model,
                tools=tools,
                hooks=hooks,
                model_settings=ModelSettings(
                    max_tokens=max_tokens,
                ),
            )
            return

        super().__init__(
            name=name,
            instructions=instructions,
            model=model,
            tools=tools,
            hooks=hooks,
            model_settings=ModelSettings(
                max_tokens=max_tokens,
            ),
        )

        return


    @function_tool
    def send_message_with_url_button(
        wrapper: RunContextWrapper[Context],
        text: str, 
        url: str, 
        display_text: str,
    ) -> str:
        """
        Creates a message with a Call-to-Action (CTA) button linking to a URL.

        WHEN TO USE:
        - ALWAYS use this tool when sending URLs/links (mandatory for all links)
        - User needs to access an external page or resource

        IMPORTANT:
        - If you need to send 2+ URLs, call this tool multiple times (once per link)
        - Each URL must be sent in a separate call with its own message

        EXTRACTION RULE:
        - Extract URL from text to url field (don't leave URLs visible in text)
        - Display_text should be action-oriented and describe the action

        Args:
            text (str): Message text, maximum 1024 characters. Example: "Click here to view the product"
            url (str): Valid URL for redirection. Example: "https://www.example.com/products/1234567890"
            display_text (str): Button text, maximum 20 characters. Example: "View Product"
        """

        text = text[:1024] if len(text) > 1024 else text
        display_text = display_text[:20] if len(display_text) > 20 else display_text
        
        broadcast = WhatsAppBroadcastHTTPClient(
            os.environ.get(
                'FLOWS_REST_ENDPOINT'
            ),
            os.environ.get(
                'FLOWS_SEND_MESSAGE_INTERNAL_TOKEN'
            )
        )

        message = {
            "text": text,
            "interaction_type": "cta_url",
            "cta_message": {
                "display_text": display_text,
                "url": url
            }
        }

        message =  {"msg": message}

        broadcast.send_direct_message(
            msg=message,
            urns=[wrapper.context.contact.get("urn")],
            project_uuid=wrapper.context.project.get("uuid"),
            user=None,
            backend="OpenAIBackend"
        )
        return

    @function_tool
    def knowledge_base_bedrock(wrapper: RunContextWrapper[Context], question: str) -> str:
        """
        Query the AWS Bedrock Knowledge Base and return the most relevant information for a given question.

        Args:
            question (str): Natural-language query. Example: "What are your shipping policies?"
        """

        client = boto3.client("bedrock-agent-runtime", region_name=settings.AWS_BEDROCK_REGION_NAME)
        content_base_uuid: str | None = wrapper.context.content_base.get("uuid")

        retrieve_params = {
            "knowledgeBaseId": settings.AWS_BEDROCK_KNOWLEDGE_BASE_ID,
            "retrievalQuery": {"text": question}
        }

        combined_filter = {
            "andAll": [
                {
                    "equals": {
                        "key": "contentBaseUuid",
                        "value": content_base_uuid
                    }
                },
                {
                    "equals": {
                        "key": "x-amz-bedrock-kb-data-source-id",
                        "value": get_datasource_id(wrapper.context.project.get("uuid"))
                    }
                }
            ]
        }

        if content_base_uuid:
            retrieve_params["retrievalConfiguration"] = {
                "vectorSearchConfiguration": {
                    "filter": combined_filter,
                }
            }

        response = client.retrieve(**retrieve_params)

        if response.get("retrievalResults"):
            all_results = []
            for result in response["retrievalResults"]:
                all_results.append(result["content"]["text"])
            return "\n".join(all_results)

        return "No response found in knowledge base."
