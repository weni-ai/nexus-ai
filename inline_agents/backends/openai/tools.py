from typing import TYPE_CHECKING, Any

import boto3

if TYPE_CHECKING:
    pass
from django.conf import settings
from openai.types.shared import Reasoning

from nexus.utils import get_datasource_id


class Supervisor:  # type: ignore[misc]
    def function_tools(self) -> list:
        return [self.knowledge_base_bedrock]

    def __init__(
        self,
        name: str,
        instructions: str,
        model: str,
        tools: list[Any],
        hooks: list | None = None,
        handoffs: list | None = None,
        prompt_override_configuration: dict | None = None,
        preview: bool = False,
        max_tokens: int | None = None,
        use_components: bool = False,
    ):
        tools.extend(self.function_tools())

        reasoning_effort = settings.OPENAI_AGENTS_REASONING_EFFORT
        reasoning_summary = settings.OPENAI_AGENTS_REASONING_SUMMARY
        parallel_tool_calls = settings.OPENAI_AGENTS_PARALLEL_TOOL_CALLS

        from agents import ModelSettings

        if model in settings.MODELS_WITH_REASONING and reasoning_effort:
            super().__init__(
                name=name,
                instructions=instructions,
                model=model,
                tools=tools,
                hooks=hooks,
                model_settings=ModelSettings(
                    max_tokens=max_tokens,
                    reasoning=Reasoning(effort=reasoning_effort, summary=reasoning_summary),
                    parallel_tool_calls=parallel_tool_calls,
                ),
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
                    parallel_tool_calls=parallel_tool_calls,
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
                parallel_tool_calls=parallel_tool_calls,
            ),
        )

        return

    from agents import function_tool

    @function_tool
    def knowledge_base_bedrock(wrapper, question: str) -> str:
        """
        Query the AWS Bedrock Knowledge Base and return the most relevant information for a given question.

        Args:
            question (str): Natural-language query. Example: "What are your shipping policies?"
        """

        client = boto3.client("bedrock-agent-runtime", region_name=settings.AWS_BEDROCK_REGION_NAME)
        content_base_uuid: str | None = wrapper.context.content_base.get("uuid")

        retrieve_params = {
            "knowledgeBaseId": settings.AWS_BEDROCK_KNOWLEDGE_BASE_ID,
            "retrievalQuery": {"text": question},
        }

        combined_filter = {
            "andAll": [
                {"equals": {"key": "contentBaseUuid", "value": content_base_uuid}},
                {
                    "equals": {
                        "key": "x-amz-bedrock-kb-data-source-id",
                        "value": get_datasource_id(wrapper.context.project.get("uuid")),
                    }
                },
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
