from typing import Any, List

import boto3
from agents import (
    Agent,
    AgentHooks,
    ModelSettings,
    RunContextWrapper,
    function_tool,
    handoff,
    FunctionToolResult,
)
from django.conf import settings
from openai.types.shared import Reasoning
from pydantic import BaseModel, Field
from inline_agents.backends.openai.entities import Context
from nexus.utils import get_datasource_id
from inline_agents.backends.openai.components_tools import COMPONENT_TOOLS
from agents.agent import ToolsToFinalOutputResult

class FinalResponse(BaseModel):
    """Modelo para a resposta final formatada"""
    final_response: str = Field(description="O resultado final da resposta que ira ser formatado")


class Supervisor(Agent):
    def function_tools(self) -> list:
        return [self.knowledge_base_bedrock]

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
        formatter_agent_instructions: str = "",
    ):
        tools.extend(self.function_tools())
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

        self.formatter_agent = self.get_formatter_agent(model, hooks, formatter_agent_instructions)
        self.format_handoff = self._create_formatter_handoff()

        agent = super().__init__(
            name=name,
            instructions=instructions,
            model=model,
            tools=tools,
            hooks=hooks,
            model_settings=ModelSettings(
                max_tokens=max_tokens,
            ),
        )
        if use_components:
            agent.handoffs = [self.format_handoff]
            agent.output_type = FinalResponse

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

    def _create_formatter_handoff(self, formatter_agent: Agent):
        """Cria o handoff para o agente formatador"""
        
        async def on_handoff_to_formatter(
            ctx: RunContextWrapper[Context],
            input_data: FinalResponse
        ):
            # Log do handoff para debug
            print(f"🔄 Handoff para formatador recebido")
            print(f"📝 Dados recebidos: {input_data.final_response[:100]}..." if len(input_data.final_response) > 100 else f"📝 Dados: {input_data.final_response}")
            
            # Aqui você pode adicionar lógica adicional, como logging ou métricas

        return handoff(
            agent=self.formatter_agent,
            tool_name_override="format_final_response",
            tool_description_override="Format the final response using appropriate JSON components. Analyze all provided information (simple message, products, options, links, context) and choose the best component automatically.",
            on_handoff=on_handoff_to_formatter,
            input_type=FinalResponse
        )

    def custom_tool_handler(self, context: RunContextWrapper[Context], tool_results: List[FunctionToolResult]) -> ToolsToFinalOutputResult:
        if tool_results:
            first_result = tool_results[0]
            return ToolsToFinalOutputResult(
                is_final_output=True,
                final_output=first_result.output
            )
        return ToolsToFinalOutputResult(
            is_final_output=False,
            final_output=None
        )

    def get_formatter_agent(self, model: str, hooks, formatter_agent_instructions: str = ""):
        formatter_agent = Agent(
            name="Response Formatter Agent",
            instructions=formatter_agent_instructions,
            model=model,
            tools=COMPONENT_TOOLS,
            hooks=hooks,
            tool_use_behavior=self.custom_tool_handler,
            model_settings=ModelSettings(
                tool_choice="required",
                parallel_tool_calls=False
            )
        )
        return formatter_agent