import ast
import json
import logging
from typing import Any, Dict, List

import boto3
from agents import Agent, ModelSettings, RunContextWrapper, function_tool
from agents.agent import FunctionToolResult, ToolsToFinalOutputResult
from agents.extensions.models.litellm_model import LitellmModel
from django.conf import settings
from openai.types.shared import Reasoning

from inline_agents.backends.openai.entities import Context
from nexus.utils import get_datasource_id

logger = logging.getLogger(__name__)

_DEBUG_PREFIX = "[is_final_output]"


def _is_final_debug(msg: str) -> None:
    logger.debug("%s %s", _DEBUG_PREFIX, msg)
    print(f"{_DEBUG_PREFIX} {msg}", flush=True)


def _trunc_preview(value: Any, max_len: int = 200) -> str:
    s = repr(value) if not isinstance(value, str) else value
    if len(s) <= max_len:
        return s
    return s[:max_len] + "..."


def _texts_from_messages_list(messages: Any) -> list[str]:
    if not isinstance(messages, list):
        return []
    parts: list[str] = []
    for item in messages:
        if isinstance(item, dict):
            t = str(item.get("text", "")).strip()
            if t:
                parts.append(t)
    return parts


def _append_tool_messages_to_hooks_state(hooks_state: Any, messages: Any, tool_name: str) -> None:
    if hooks_state is None:
        return
    texts = _texts_from_messages_list(messages)
    if not texts:
        return
    if not hasattr(hooks_state, "tool_messages_for_sqs"):
        return
    hooks_state.tool_messages_for_sqs.extend(texts)
    _is_final_debug(
        f"I non_final_tool_messages tool={tool_name} appended_count={len(texts)} "
        f"total_accumulated={len(hooks_state.tool_messages_for_sqs)}"
    )


class AgentModel:
    def get_model(self, model: str, user_model_credentials: Dict[str, Any]) -> LitellmModel | str:
        if "litellm" in model:
            cleaned_model = model.replace("litellm/", "")
            kwargs = {
                "model": cleaned_model,
            }

            if "vertex" in model:
                return LitellmModel(**kwargs)

            if user_model_credentials.get("api_key"):
                kwargs["api_key"] = user_model_credentials.get("api_key")
            if user_model_credentials.get("api_base"):
                kwargs["base_url"] = user_model_credentials.get("api_base")

            return LitellmModel(**kwargs)
        return model

    def custom_tool_handler(
        self, context: RunContextWrapper[Any], tool_results: List[FunctionToolResult]
    ) -> ToolsToFinalOutputResult:
        agent_label = type(self).__name__
        n = len(tool_results) if tool_results else 0
        _is_final_debug(f"A handler_enter agent={agent_label} tool_results_count={n}")

        if not tool_results:
            _is_final_debug("D return is_final_output=False (no tool_results)")
            return ToolsToFinalOutputResult(is_final_output=False, final_output=None)

        hooks_state = getattr(context.context, "hooks_state", None)

        for result in tool_results:
            raw_out = result.output
            tool_name = getattr(getattr(result, "tool", None), "name", "?")
            _is_final_debug(
                f"A tool={tool_name} raw_output_type={type(raw_out).__name__} raw_preview={_trunc_preview(raw_out)}"
            )

            parsed = self._try_parse_output(raw_out)
            if isinstance(parsed, dict):
                keys_preview = list(parsed.keys())
                has_msgs = "messages_sent" in parsed
                io_flag = bool(parsed.get("is_final_output"))
                _is_final_debug(
                    f"B parsed=dict keys={keys_preview} is_final_output={io_flag} has_messages_sent={has_msgs}"
                )
            else:
                _is_final_debug(f"B parsed=non-dict type={type(parsed).__name__} preview={_trunc_preview(parsed)}")

            if isinstance(parsed, dict) and parsed.get("is_final_output", False):
                messages_sent = parsed.get("messages_sent") or []
                # Only the top-level manager run should set this; nested collaborator runs share
                # hooks_state and would otherwise skip dispatch while the manager may still respond.
                if hooks_state is not None and agent_label == "Supervisor":
                    hooks_state.skip_outgoing_dispatch = True
                _is_final_debug(
                    f"C is_final_output=True tool={tool_name} agent={agent_label}"
                    f"messages_sent_len={len(messages_sent)}"
                    f"skip_outgoing_dispatch_set={hooks_state is not None and agent_label == 'Supervisor'}"
                )
                payload = {"is_final_output": True, "messages_sent": messages_sent}
                final_str = json.dumps(payload, ensure_ascii=False)
                _is_final_debug(
                    f"D return ToolsToFinalOutputResult(is_final_output=True) final_preview={_trunc_preview(final_str)}"
                )
                return ToolsToFinalOutputResult(is_final_output=True, final_output=final_str)

            if isinstance(parsed, dict) and not parsed.get("is_final_output") and "messages" in parsed:
                _append_tool_messages_to_hooks_state(hooks_state, parsed.get("messages"), tool_name=tool_name)

        _is_final_debug("D return is_final_output=False (no matching tool)")
        return ToolsToFinalOutputResult(is_final_output=False, final_output=None)

    @staticmethod
    def _try_parse_output(raw_output: Any) -> Any:
        if isinstance(raw_output, dict):
            return raw_output
        if isinstance(raw_output, list):
            return raw_output
        if isinstance(raw_output, str):
            try:
                return json.loads(raw_output)
            except json.JSONDecodeError:
                try:
                    return ast.literal_eval(raw_output)
                except (ValueError, SyntaxError):
                    pass
        return raw_output


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

        model = self.get_model(model_name, user_model_credentials)
        model_settings_kw = dict(model_settings)
        if isinstance(model, LitellmModel):
            model_settings_kw["include_usage"] = True
        super().__init__(
            name=name,
            instructions=instructions,
            tools=tools,
            model=model,
            hooks=hooks,
            model_settings=ModelSettings(**model_settings_kw),
            tool_use_behavior=self.custom_tool_handler,
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
        parallel_tool_calls: bool = False,
        extra_args: dict | None = None,
    ):
        tools.extend(self.function_tools())

        model = self.get_model(model, user_model_credentials)

        model_settings_kwargs: Dict[str, Any] = {
            "parallel_tool_calls": parallel_tool_calls,
            "extra_args": extra_args,
        }
        if max_tokens is not None:
            model_settings_kwargs["max_tokens"] = max_tokens
        if isinstance(model, LitellmModel):
            model_settings_kwargs["include_usage"] = True

        if model_has_reasoning and reasoning_effort:
            model_settings_kwargs["reasoning"] = Reasoning(effort=reasoning_effort, summary=reasoning_summary)

        super().__init__(
            name=name,
            instructions=instructions,
            model=model,
            tools=tools,
            hooks=hooks,
            model_settings=ModelSettings(**model_settings_kwargs),
            tool_use_behavior=self.custom_tool_handler,
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
