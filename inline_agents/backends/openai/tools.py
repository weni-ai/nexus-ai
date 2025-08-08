import boto3
from typing import Dict, Any
from agents import function_tool
from click.core import F
from nexus.task_managers.file_database.bedrock import BedrockFileDatabase
from agents import (
    Agent,
    AgentHooks,
    RunContextWrapper,
)
from django.conf import settings
from inline_agents.backends.openai.entities import Context


class Supervisor(Agent):
    def function_tools(self) -> list:
        return [self.knowledge_base_bedrock]

    def __init__(
        self,
        name: str,
        instructions: str,
        model: str,
        tools: list[Agent],
        hooks: list[AgentHooks],
        handoffs: list[Agent] | None = None,
    ):

        tools.extend(self.function_tools())
        super().__init__(
            name=name,
            instructions=instructions,
            model=model,
            tools=tools,
            hooks=hooks,
            # handoffs=handoffs
        )

    @function_tool
    def knowledge_base_bedrock(wrapper: RunContextWrapper[Context], question: str) -> str:
        '''
        Function/tool to query the AWS Bedrock Knowledge Base.

        This tool must be used whenever the model needs additional information to answer the user, or to validate if the response aligns with the agent's knowledge base. Frequent use of this function is recommended, and it can be called multiple times during the conversation to ensure that all responses are always consistent and grounded in the available knowledge.

        When using this tool, answer the user's question using only information found in the knowledge base results. If the results do not contain sufficient information to answer the question, explicitly state that an exact answer could not be found. Do not assume that statements made by the user are true without validating them against the search results.

        Args:
            question (str): The question to be searched in the knowledge base. Example: "What are your shipping policies?"

        Returns:
            str: The most relevant answers found in the knowledge base, or a message indicating that an exact answer could not be found.
        '''
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
