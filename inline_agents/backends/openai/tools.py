from typing import TYPE_CHECKING, Any, Dict

import boto3

if TYPE_CHECKING:
    pass
from agents import Agent, ModelSettings, RunContextWrapper, function_tool
from agents.extensions.models.litellm_model import LitellmModel
from django.conf import settings
from openai.types.shared import Reasoning

from inline_agents.backends.openai.entities import Context
from nexus.utils import get_datasource_id


class AgentModel:
    def get_model(self, model: str, user_model_credentials: Dict[str, Any]) -> LitellmModel | str:
        if "litellm" in model:
            cleaned_model = model.replace("litellm/", "")
            kwargs = {
                "model": cleaned_model,
                "api_key": user_model_credentials.get("api_key"),
            }
            if user_model_credentials.get("api_base"):
                kwargs["base_url"] = user_model_credentials.get("api_base")

            return LitellmModel(**kwargs)
        return model


class Collaborator(Agent[Context], AgentModel):  # type: ignore[misc]
    def __init__(
        self,
        name: str,
        instructions: str,
        tools: list,
        foundation_model: str,
        user_model_credentials: Dict[str, str],
        hooks,
        model_settings: Dict[str, Any],
        collaborator_configurations: Dict[str, Any],
        model_has_reasoning: bool = False,
    ):
        if collaborator_configurations.get("override_collaborators_foundation_model"):
            model_name = collaborator_configurations.get("collaborators_foundation_model")
        else:
            model_name = foundation_model

        super().__init__(
            name=name,
            instructions=instructions,
            tools=tools,
            model=self.get_model(model_name, user_model_credentials),
            hooks=hooks,
            model_settings=ModelSettings(**model_settings),
        )


class Supervisor(Agent[Context], AgentModel):  # type: ignore[misc]
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
        user_model_credentials: Dict[str, str] = None,
        model_has_reasoning: bool = False,
        reasoning_effort: str = "",
        reasoning_summary: str = "",
    ):
        tools.extend(self.function_tools())
        parallel_tool_calls = settings.OPENAI_AGENTS_PARALLEL_TOOL_CALLS

        model = self.get_model(model, user_model_credentials)

        model_settings_kwargs = {
            "max_tokens": max_tokens,
            "parallel_tool_calls": parallel_tool_calls,
        }

        if model_has_reasoning and reasoning_effort:
            model_settings_kwargs["reasoning"] = Reasoning(effort=reasoning_effort, summary=reasoning_summary)

        super().__init__(
            name=name,
            instructions=instructions,
            model=model,
            tools=tools,
            hooks=hooks,
            model_settings=ModelSettings(**model_settings_kwargs),
        )

    @function_tool
    def knowledge_base_bedrock(ctx: RunContextWrapper[Context], question: str) -> str:
        """
        Query the AWS Bedrock Knowledge Base and return the most relevant information for a given question.

        Args:
            question (str): Natural-language query. Example: "What are your shipping policies?"
        """

        client = boto3.client("bedrock-agent-runtime", region_name=settings.AWS_BEDROCK_REGION_NAME)
        content_base_uuid: str | None = ctx.context.content_base.get("uuid")

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
                        "value": get_datasource_id(ctx.context.project.get("uuid")),
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
