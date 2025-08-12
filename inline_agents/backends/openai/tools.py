import boto3
from typing import Dict, Any
from agents import function_tool
from click.core import F
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase
from agents import (
    Agent,
    AgentHooks,
    RunContextWrapper,
    ModelSettings,
)
from django.conf import settings
from inline_agents.backends.openai.entities import Context
from openai.types.shared import Reasoning


class Supervisor(Agent):
    def function_tools(self) -> list:
        return [self.knowledge_base_bedrock]

    def __init__(
        self,
        name: str,
        instructions: str,
        model: str,
        tools: list[Any],
        hooks: list[AgentHooks],
        handoffs: list[Agent] | None = None,
        prompt_override_configuration: dict | None = None,
    ):

        tools.extend(self.function_tools())
        super().__init__(
            name=name,
            instructions=instructions,
            model=model,
            tools=tools,
            hooks=hooks,
            model_settings=ModelSettings(
                reasoning=Reasoning(
                    effort="medium",
                    summary="auto"
                ),
            )
        )

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
                        "value": settings.AWS_BEDROCK_DATASOURCE_ID
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
