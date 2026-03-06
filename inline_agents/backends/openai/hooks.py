import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import pendulum
import sentry_sdk
from django.utils.text import slugify

try:
    from agents import AgentHooks, RunHooks
except Exception:  # Fallback for test environments where agents fails to import
    AgentHooks = object  # type: ignore[assignment]
    RunHooks = object  # type: ignore[assignment]

if TYPE_CHECKING:
    pass
from agents.extensions.models.litellm_model import LitellmModel
from django.conf import settings
from langfuse import get_client

from inline_agents.adapter import DataLakeEventAdapter
from inline_agents.backends.openai.entities import FinalResponse, HooksState

logger = logging.getLogger(__name__)


def _usage_dict_from_request_entry(entry: Any) -> Optional[Dict[str, int]]:
    """Build Langfuse usage_details from a single request_usage_entry (one LLM call)."""
    if entry is None:
        return None
    try:
        input_tokens = getattr(entry, "input_tokens", 0) or 0
        output_tokens = getattr(entry, "output_tokens", 0) or 0
        input_details = getattr(entry, "input_tokens_details", None)
        cached = 0
        if input_details is not None:
            cached = getattr(input_details, "cached_tokens", 0) or 0
        if input_tokens == 0 and output_tokens == 0:
            return None
        return {
            "input": input_tokens,
            "output": output_tokens,
            "cache_read_input_tokens": cached,
        }
    except Exception as e:
        logger.debug("Could not build usage_dict from request entry: %s", e)
        return None


def _usage_dict_from_response_usage(usage: Any) -> Optional[Dict[str, int]]:
    """Build Langfuse usage_details from response.usage (e.g. OpenAI-style)."""
    if usage is None:
        return None
    try:
        input_tokens = getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", 0) or 0
        input_details = getattr(usage, "input_tokens_details", None)
        cached = 0
        if input_details is not None:
            cached = getattr(input_details, "cached_tokens", 0) or 0
        if input_tokens == 0 and output_tokens == 0:
            return None
        return {
            "input": input_tokens,
            "output": output_tokens,
            "cache_read_input_tokens": cached,
        }
    except Exception as e:
        logger.debug("Could not build usage_dict from response usage: %s", e)
        return None


def _update_langfuse_current_generation_usage(usage_dict: Dict[str, int]) -> None:
    """Update the current Langfuse generation with usage_details so cache appears in the same request."""
    if not usage_dict:
        return
    try:
        langfuse = get_client()
        update = getattr(langfuse, "update_current_generation", None)
        if callable(update):
            update(usage_details=usage_dict)
    except Exception as e:
        logger.debug("Could not update current Langfuse generation with usage: %s", e)


def _get_agent_slug(agent, hooks_state=None) -> str:
    """
    Get the agent slug from the agent object.
    For supervisor agent, it uses name="manager" which is a fixed value.
    For Response Formatter Agent, use the last active agent slug if available.
    """
    # Response Formatter Agent should use the slug of the last agent that executed
    if agent.name == "Response Formatter Agent" and hooks_state:
        if hooks_state.last_active_agent_slug:
            logger.debug(
                f"[_get_agent_slug] Formatter agent using last_active_agent_slug: {hooks_state.last_active_agent_slug}"
            )
            return hooks_state.last_active_agent_slug
        else:
            logger.warning(
                "[_get_agent_slug] Formatter agent but last_active_agent_slug is None. "
                "This may indicate that no collaborator executed before the formatter."
            )

    if " " not in agent.name:
        return agent.name

    return slugify(agent.name)


def _get_agent_model(agent) -> str:
    if isinstance(agent.model, LitellmModel):
        return agent.model.model
    return agent.model


def _get_events_from_tool_result(
    result, tool_name: str, hooks_state: HooksState, project_uuid: str, contact_urn: str
) -> List:
    """Extract events list from tool result (str or dict). Returns empty list on error."""
    if isinstance(result, str):
        try:
            result_json = json.loads(result)
            try:
                return hooks_state.get_events(result_json, tool_name)
            except Exception as e:
                logger.error(f"Error in get_events for tool '{tool_name}': {e}")
                sentry_sdk.set_context(
                    "get_events_error",
                    {"tool_name": tool_name, "project_uuid": project_uuid, "contact_urn": contact_urn},
                )
                sentry_sdk.capture_exception(e)
                return []
        except Exception:
            return []
    if isinstance(result, dict):
        try:
            return hooks_state.get_events(result, tool_name)
        except Exception as e:
            logger.error(f"Error in get_events for tool '{tool_name}': {e}")
            sentry_sdk.set_context(
                "get_events_error",
                {"tool_name": tool_name, "project_uuid": project_uuid, "contact_urn": contact_urn},
            )
            sentry_sdk.capture_exception(e)
            return []
    return []


def _normalize_events_to_list(events, tool_name: str, project_uuid: str) -> List:
    """Parse events (str/dict/list) into a list of event dicts. Returns empty list if invalid."""
    if not events or events == "[]" or events == []:
        return []
    if isinstance(events, str):
        try:
            events = json.loads(events)
        except json.JSONDecodeError as e:
            sentry_sdk.set_context("custom event to data lake", {"event_data": events})
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.capture_exception(e)
            return []
    if isinstance(events, dict):
        events = events.get("events", [])
    if isinstance(events, list) and len(events) > 0:
        return events
    return []


def _result_to_value(result):
    """Normalize tool result to a value suitable for tool_result_data."""
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            return json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return result
    return result


class TraceHandler:
    def __init__(
        self,
        event_manager_notify,
        preview,
        rationale_switch,
        language,
        user_email,
        session_id,
        msg_external_id,
        turn_off_rationale,
        hooks_state,
        message_uuid=None,
    ):
        self.event_manager_notify = event_manager_notify
        self.preview = preview
        self.rationale_switch = rationale_switch
        self.language = language
        self.user_email = user_email
        self.session_id = session_id
        self.msg_external_id = msg_external_id
        self.turn_off_rationale = turn_off_rationale
        self.hooks_state = hooks_state
        self.message_uuid = message_uuid

    async def send_trace(self, context_data, agent_name, trace_type, trace_data=None, tool_name=""):
        if trace_data is None:
            trace_data = {}
        standardized_event = {
            "config": {
                "agentName": agent_name,
                "type": trace_type,
                "toolName": tool_name,
            },
            "trace": trace_data,
        }
        self.hooks_state.trace_data.append({"trace": standardized_event})
        await self.event_manager_notify(
            event="inline_trace_observers_async",
            inline_traces=standardized_event,
            user_input=context_data.input_text,
            contact_urn=context_data.contact.get("urn"),
            project_uuid=context_data.project.get("uuid"),
            send_message_callback=None,
            preview=self.preview,
            rationale_switch=self.rationale_switch,
            language=self.language,
            user_email=self.user_email,
            session_id=self.session_id,
            msg_external_id=self.msg_external_id,
            turn_off_rationale=self.turn_off_rationale,
            channel_uuid=context_data.contact.get("channel_uuid"),
        )

    async def save_trace_data(
        self,
        trace_events: List[Dict],
        project_uuid: str,
        input_text: str,
        contact_urn: str,
        full_response: str,
        preview: bool,
        session_id: str,
        contact_name: str,
        channel_uuid: str,
    ):
        await self.event_manager_notify(
            event="save_inline_trace_events",
            trace_events=trace_events,
            project_uuid=project_uuid,
            user_input=input_text,
            contact_urn=contact_urn,
            agent_response=full_response,
            preview=preview,
            session_id=session_id,
            source_type="agent",  # If user message, source_type="user"
            contact_name=contact_name,
            channel_uuid=channel_uuid,
            message_uuid=self.message_uuid,
        )


class RunnerHooks(RunHooks):  # type: ignore[misc]
    def __init__(
        self,
        supervisor_name: str,
        preview: bool,
        rationale_switch: bool,
        language: str,
        user_email: str,
        session_id: str,
        msg_external_id: str,
        turn_off_rationale: bool,
        event_manager_notify: callable,
        agents: list,
        hooks_state: HooksState,
        message_uuid: str = None,
    ):
        self.trace_handler = TraceHandler(
            event_manager_notify=event_manager_notify,
            preview=preview,
            rationale_switch=rationale_switch,
            language=language,
            user_email=user_email,
            session_id=session_id,
            msg_external_id=msg_external_id,
            turn_off_rationale=turn_off_rationale,
            hooks_state=hooks_state,
            message_uuid=message_uuid,
        )
        self.agents = agents
        self.supervisor_name = supervisor_name
        self.rationale_switch = rationale_switch
        self.language = language
        self.user_email = user_email
        self.session_id = session_id
        self.msg_external_id = msg_external_id
        self.turn_off_rationale = turn_off_rationale
        self.preview = preview
        self.list_handoffs_requested = []
        self.event_manager_notify = event_manager_notify
        self.agents_names = []
        self.knowledge_base_tool = None
        self.current_agent = None

        for agent in self.agents:
            self.agents_names.append(agent.get("agentName"))

        try:
            super().__init__()  # type: ignore
        except Exception:
            pass

    async def on_llm_start(self, context, agent, system_prompt, input_items) -> None:
        logger.info("[HOOK] Acionando o modelo.")
        context_data = context.context
        await self.trace_handler.send_trace(
            context_data, _get_agent_slug(agent, self.trace_handler.hooks_state), "invoking_model"
        )

    async def on_llm_end(self, context, agent, response, **kwargs):
        context_data = context.context
        # Update the current Langfuse generation (this LLM request) with usage including cache
        # so cache_read_input_tokens appears in the same "Usage breakdown" as input/output.
        # Applies to all providers used via OpenAIBackend: OpenAI (gpt-*), Gemini (LiteLLM),
        # Anthropic/Claude (LiteLLM), and any other model routed through openai-agents/LiteLLM.
        try:
            usage_dict = None
            usage = getattr(context, "usage", None)
            if usage is not None:
                request_entries = getattr(usage, "request_usage_entries", None) or []
                if request_entries:
                    last_entry = request_entries[-1]
                    usage_dict = _usage_dict_from_request_entry(last_entry)
            if usage_dict is None and hasattr(response, "usage"):
                usage_dict = _usage_dict_from_response_usage(response.usage)
            if usage_dict:
                _update_langfuse_current_generation_usage(usage_dict)
        except Exception as e:
            logger.debug("[RunnerHooks] on_llm_end: could not update Langfuse generation usage: %s", e)

        for reasoning_item in response.output:
            if (
                getattr(reasoning_item, "type", None) == "reasoning"
                and hasattr(reasoning_item, "summary")
                and reasoning_item.summary
            ):
                logger.info("[HOOK] Pensando.")
                for summary in reasoning_item.summary:
                    trace_data = {
                        "collaboratorName": "",
                        "eventTime": pendulum.now().to_iso8601_string(),
                        "trace": {
                            "orchestrationTrace": {
                                "rationale": {"text": summary.text, "reasoningId": reasoning_item.id}
                            }
                        },
                    }
                    await self.trace_handler.send_trace(
                        context_data, _get_agent_slug(agent, self.trace_handler.hooks_state), "thinking", trace_data
                    )
        logger.info("[HOOK] Resposta do modelo recebida.")
        await self.trace_handler.send_trace(
            context_data, _get_agent_slug(agent, self.trace_handler.hooks_state), "model_response_received"
        )


class CollaboratorHooks(AgentHooks):  # type: ignore[misc]
    def __init__(
        self,
        agent_name: str,
        data_lake_event_adapter: DataLakeEventAdapter,
        hooks_state: HooksState,
        event_manager_notify: callable = None,
        preview: bool = False,
        rationale_switch: bool = False,
        language: str = "en",
        user_email: str = None,
        session_id: str = None,
        msg_external_id: str = None,
        turn_off_rationale: bool = False,
        conversation: Optional[object] = None,
    ):
        self.trace_handler = TraceHandler(
            event_manager_notify=event_manager_notify,
            preview=preview,
            rationale_switch=rationale_switch,
            language=language,
            user_email=user_email,
            session_id=session_id,
            msg_external_id=msg_external_id,
            turn_off_rationale=turn_off_rationale,
            hooks_state=hooks_state,
        )
        self.agent_name = agent_name
        self.data_lake_event_adapter = data_lake_event_adapter
        self.hooks_state = hooks_state
        self.preview = preview
        self.conversation = conversation

    async def on_start(self, context, agent):
        agent_slug = _get_agent_slug(agent, self.hooks_state)
        self.hooks_state.last_active_agent_slug = agent_slug
        logger.info(f"[HOOK] Atribuindo tarefa ao agente '{agent_slug}'.")
        input_text = self.hooks_state.tool_calls.get(agent_slug, {})
        if isinstance(input_text, str):
            try:
                input_text = json.loads(input_text).get("question", "")
            except Exception:
                input_text = input_text

        trace_data = {
            "orchestrationTrace": {
                "invocationInput": {
                    "agentCollaboratorInvocationInput": {
                        "agentCollaboratorAliasArn": f"INLINE_AGENT/{agent_slug}",
                        "agentCollaboratorName": agent_slug,
                        "input": {
                            "text": input_text,
                            "type": "TEXT",
                        },
                    },
                    "invocationType": "AGENT_COLLABORATOR",
                }
            }
        }
        context_data = context.context
        await self.trace_handler.send_trace(context_data, agent_slug, "delegating_to_agent", trace_data)
        self.data_lake_event_adapter.to_data_lake_event(
            project_uuid=context_data.project.get("uuid"),
            contact_urn=context_data.contact.get("urn"),
            agent_data={
                "agent_name": _get_agent_slug(agent, self.hooks_state),
                "input_text": context_data.input_text,
            },
            foundation_model=_get_agent_model(agent),
            backend="openai",
            channel_uuid=context_data.contact.get("channel_uuid"),
            conversation=self.conversation,
        )

    async def tool_started(self, context, agent, tool):
        context_data = context.context
        tool_info = self.hooks_state.get_tool_info(tool.name)
        parameters = tool_info.get("parameters", [])

        agent_slug = _get_agent_slug(agent, self.hooks_state)
        self.hooks_state.last_active_agent_slug = agent_slug
        logger.info(f"[HOOK] Executando ferramenta '{tool.name}'.")
        logger.info(f"[HOOK] Agente '{agent_slug}' vai usar a ferramenta '{tool.name}'.")
        trace_data = {
            "collaboratorName": agent_slug,
            "eventTime": pendulum.now().to_iso8601_string(),
            "sessionId": context_data.session.get_session_id(),
            "trace": {
                "orchestrationTrace": {
                    "invocationInput": {
                        "actionGroupInvocationInput": {
                            "actionGroupName": tool.name,
                            "executionType": "LAMBDA",
                            "function": tool.name,
                            "parameters": parameters,
                        },
                    }
                }
            },
        }
        logger.debug("==============tool_calls================")
        logger.debug(f"Tool name: {tool.name}")
        logger.debug(f"Tool info: {self.hooks_state.tool_info}")
        logger.debug(f"Trace data: {trace_data}")
        logger.debug("==========================================")
        await self.trace_handler.send_trace(context_data, agent_slug, "executing_tool", trace_data, tool_name=tool.name)

    async def on_tool_end(self, context, agent, tool, result):
        # Emit the "tool started" trace (e.g. for preview).
        await self.tool_started(context, agent, tool)

        context_data = context.context
        project_uuid = context_data.project.get("uuid")
        tool_info = self.hooks_state.get_tool_info(tool.name)
        parameters = tool_info.get("parameters", [])
        # If framework already called tool_started, index points at session_attributes (no
        # "parameters"); params are in the previous entry. Use them so tool_result has params.
        if not parameters and tool.name in self.hooks_state.tool_info:
            executions = self.hooks_state.tool_info[tool.name]
            idx = self.hooks_state.tool_info_index.get(tool.name, 0)
            if idx > 0 and idx <= len(executions):
                params_entry = executions[idx - 1]
                parameters = params_entry.get("parameters", [])
        self.hooks_state.advance_tool_info_index(tool.name)

        logger.info(f"[HOOK] Resultado da ferramenta '{tool.name}' recebido {result}.")

        contact_urn = context_data.contact.get("urn", "unknown")
        events = _get_events_from_tool_result(result, tool.name, self.hooks_state, project_uuid, contact_urn)
        events_list = _normalize_events_to_list(events, tool.name, project_uuid)
        if events_list:
            logger.info(f"[HOOK] Eventos da ferramenta '{tool.name}': {events_list}")
            try:
                self.data_lake_event_adapter.custom_event_data(
                    event_data=events_list,
                    project_uuid=project_uuid,
                    contact_urn=context_data.contact.get("urn"),
                    channel_uuid=context_data.contact.get("channel_uuid"),
                    agent_name=_get_agent_slug(agent, self.hooks_state),
                    preview=self.preview,
                    conversation=self.conversation,
                )
            except Exception as e:
                logger.error(f"Error calling custom_event_data in CollaboratorHooks: {str(e)}")
                sentry_sdk.capture_exception(e)
        elif "human" in tool.name.lower() or "support" in tool.name.lower():
            logger.warning(
                f"No events found for tool '{tool.name}'. "
                f"This may result in missing record in contact history. "
                f"Project: {project_uuid}, Contact: {contact_urn}"
            )

        result_value = _result_to_value(result)
        try:
            self.data_lake_event_adapter.to_data_lake_event(
                project_uuid=project_uuid,
                contact_urn=context_data.contact.get("urn"),
                tool_result_data={
                    "tool_name": tool.name,
                    "result": result_value,
                    "parameters": parameters,
                    "function_name": self.hooks_state.lambda_names.get(tool.name, {}).get("function_name"),
                },
                agent_data={"agent_name": agent.name},
                foundation_model=_get_agent_model(agent),
                backend="openai",
                channel_uuid=context_data.contact.get("channel_uuid"),
                conversation=self.conversation,
            )
        except Exception as e:
            logger.error(f"Error sending tool result event for tool '{tool.name}': {str(e)}")
            sentry_sdk.set_context(
                "tool_result_event_error",
                {"tool_name": tool.name, "project_uuid": project_uuid, "contact_urn": contact_urn},
            )
            sentry_sdk.capture_exception(e)

        agent_slug = _get_agent_slug(agent, self.hooks_state)
        self.hooks_state.last_active_agent_slug = agent_slug
        trace_data = {
            "collaboratorName": agent_slug,
            "eventTime": pendulum.now().to_iso8601_string(),
            "sessionId": context_data.session.get_session_id(),
            "trace": {
                "orchestrationTrace": {
                    "observation": {
                        "actionGroupInvocationOutput": {
                            "text": result,
                            "tool_name": tool.name,
                            "parameters": parameters,
                        },
                    }
                }
            },
        }
        await self.trace_handler.send_trace(
            context_data, agent_slug, "tool_result_received", trace_data, tool_name=tool.name
        )

    async def on_end(self, context, agent, output):
        logger.info(f"[HOOK] Enviando resposta ao manager. {output}")
        context_data = context.context
        agent_slug = _get_agent_slug(agent, self.hooks_state)
        # Update last_active_agent_slug when collaborator finishes
        self.hooks_state.last_active_agent_slug = agent_slug
        trace_data = {
            "eventTime": pendulum.now().to_iso8601_string(),
            "sessionId": context_data.session.get_session_id(),
            "trace": {
                "orchestrationTrace": {
                    "observation": {
                        "agentCollaboratorInvocationOutput": {
                            "agentCollaboratorName": agent_slug,
                            "output": {"text": output, "type": "TEXT"},
                        },
                        "type": "AGENT_COLLABORATOR",
                    }
                }
            },
        }
        await self.trace_handler.send_trace(context_data, agent_slug, "forwarding_to_manager", trace_data)


class SupervisorHooks(AgentHooks):  # type: ignore[misc]
    def __init__(
        self,
        agent_name: str,
        preview: bool,
        agents: list,
        data_lake_event_adapter: DataLakeEventAdapter,
        event_manager_notify: callable,
        hooks_state: HooksState,
        rationale_switch: bool = False,
        language: str = "en",
        knowledge_base_tool: Optional[str] = None,
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
        msg_external_id: Optional[str] = None,
        turn_off_rationale: bool = False,
        conversation: Optional[object] = None,
        use_components: bool = False,
        **kwargs,
    ):
        message_uuid = kwargs.pop("message_uuid", None)
        self.trace_handler = TraceHandler(
            event_manager_notify=event_manager_notify,
            preview=preview,
            rationale_switch=rationale_switch,
            language=language,
            user_email=user_email,
            session_id=session_id,
            msg_external_id=msg_external_id,
            turn_off_rationale=turn_off_rationale,
            hooks_state=hooks_state,
            message_uuid=message_uuid,
        )
        self.agent_name = agent_name
        self.preview = preview
        self.agents = agents
        self.knowledge_base_tool = knowledge_base_tool
        self.data_lake_event_adapter = data_lake_event_adapter
        self.hooks_state = hooks_state
        self.conversation = conversation
        self.use_components = use_components
        # this field is updated before calling formatter agent
        self.save_components_trace = False

        try:
            super().__init__()  # type: ignore
        except Exception:
            pass

    def set_knowledge_base_tool(self, knowledge_base_tool: str):
        self.knowledge_base_tool = knowledge_base_tool

    async def on_start(self, context, agent):
        logger.info(f"[HOOK] Agente '{_get_agent_slug(agent, self.hooks_state)}' iniciado.")

    async def tool_started(self, context, agent, tool):
        context_data = context.context
        tool_info = self.hooks_state.get_tool_info(tool.name)
        parameters = tool_info.get("parameters", [])

        if tool.name == self.knowledge_base_tool:
            trace_data = {
                "eventTime": pendulum.now().to_iso8601_string(),
                "sessionId": context_data.session.get_session_id(),
                "trace": {
                    "orchestrationTrace": {
                        "invocationInput": {
                            "invocationType": "KNOWLEDGE_BASE",
                            "knowledgeBaseLookupInput": {
                                "knowledgeBaseId": settings.AWS_BEDROCK_KNOWLEDGE_BASE_ID,
                                "text": context_data.input_text,
                            },
                        }
                    }
                },
            }
            await self.trace_handler.send_trace(
                context_data, _get_agent_slug(agent, self.hooks_state), "searching_knowledge_base", trace_data
            )
        elif tool.name not in self.hooks_state.agents_names:
            agent_slug = _get_agent_slug(agent, self.hooks_state)
            logger.info(f"[HOOK] Agente '{agent_slug}' vai usar a ferramenta '{tool.name}'.")
            trace_data = {
                "collaboratorName": agent_slug,
                "eventTime": pendulum.now().to_iso8601_string(),
                "sessionId": context_data.session.get_session_id(),
                "trace": {
                    "orchestrationTrace": {
                        "invocationInput": {
                            "actionGroupInvocationInput": {
                                "actionGroupName": tool.name,
                                "executionType": "LAMBDA",
                                "function": tool.name,
                                "parameters": parameters,
                            },
                        }
                    }
                },
            }
            await self.trace_handler.send_trace(
                context_data, agent_slug, "executing_tool", trace_data, tool_name=tool.name
            )

    async def _send_tool_result_to_data_lake(
        self,
        context_data,
        project_uuid,
        contact_urn,
        agent,
        tool,
        parameters,
        result_value,
        function_name,
    ):
        """Send a single tool_result event to data lake. function_name is None for knowledge base."""
        try:
            self.data_lake_event_adapter.to_data_lake_event(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                tool_result_data={
                    "tool_name": tool.name,
                    "result": result_value,
                    "parameters": parameters,
                    "function_name": function_name,
                },
                agent_data={"agent_name": agent.name},
                foundation_model=_get_agent_model(agent),
                backend="openai",
                channel_uuid=context_data.contact.get("channel_uuid"),
                conversation=self.conversation,
            )
        except Exception as e:
            logger.error(f"Error sending tool result event for tool '{tool.name}': {str(e)}")
            sentry_sdk.set_context(
                "tool_result_event_error",
                {"tool_name": tool.name, "project_uuid": project_uuid, "contact_urn": contact_urn},
            )
            sentry_sdk.capture_exception(e)

    async def _on_tool_end_knowledge_base(self, context, agent, tool, result, context_data, project_uuid, parameters):
        """Handle on_tool_end for knowledge base tool."""
        trace_data = {
            "eventTime": pendulum.now().to_iso8601_string(),
            "sessionId": context_data.session.get_session_id(),
            "trace": {
                "orchestrationTrace": {
                    "observation": {"knowledgeBaseLookupOutput": {"retrievedReferences": result}},
                }
            },
        }
        await self.trace_handler.send_trace(context_data, agent.name, "search_result_received", trace_data)
        result_value = _result_to_value(result)
        await self._send_tool_result_to_data_lake(
            context_data, project_uuid, context_data.contact.get("urn"), agent, tool, parameters, result_value, None
        )
        await self.trace_handler.send_trace(
            context_data, _get_agent_slug(agent, self.hooks_state), "search_result_received", trace_data
        )

    async def _on_tool_end_regular_tool(self, context, agent, tool, result, context_data, project_uuid, parameters):
        """Handle on_tool_end for regular (non-agent) tools."""
        contact_urn = context_data.contact.get("urn", "unknown")
        events = _get_events_from_tool_result(result, tool.name, self.hooks_state, project_uuid, contact_urn)
        events_list = _normalize_events_to_list(events, tool.name, project_uuid)
        if events_list:
            logger.info(f"[HOOK] Eventos da ferramenta '{tool.name}': {events_list}")
            try:
                self.data_lake_event_adapter.custom_event_data(
                    event_data=events_list,
                    project_uuid=project_uuid,
                    contact_urn=context_data.contact.get("urn"),
                    channel_uuid=context_data.contact.get("channel_uuid"),
                    agent_name=_get_agent_slug(agent, self.hooks_state),
                    preview=self.preview,
                    conversation=self.conversation,
                )
            except Exception as e:
                logger.error(f"Error calling custom_event_data in SupervisorHooks: {str(e)}")
                sentry_sdk.capture_exception(e)

        result_value = _result_to_value(result)
        function_name = self.hooks_state.lambda_names.get(tool.name, {}).get("function_name")
        contact_urn = context_data.contact.get("urn")
        await self._send_tool_result_to_data_lake(
            context_data, project_uuid, contact_urn, agent, tool, parameters, result_value, function_name
        )
        agent_slug = _get_agent_slug(agent, self.hooks_state)
        trace_data = {
            "collaboratorName": agent_slug,
            "eventTime": pendulum.now().to_iso8601_string(),
            "sessionId": context_data.session.get_session_id(),
            "trace": {
                "orchestrationTrace": {
                    "observation": {
                        "actionGroupInvocationOutput": {
                            "text": result,
                            "tool_name": tool.name,
                            "parameters": parameters,
                        },
                    }
                }
            },
        }
        await self.trace_handler.send_trace(
            context_data, agent_slug, "tool_result_received", trace_data, tool_name=tool.name
        )

    async def on_tool_end(self, context, agent, tool, result):
        # Emit the "tool started" trace (e.g. for preview).
        await self.tool_started(context, agent, tool)

        context_data = context.context
        project_uuid = context_data.project.get("uuid")
        tool_info = self.hooks_state.get_tool_info(tool.name)
        parameters = tool_info.get("parameters", [])
        # If framework already called tool_started, index may point at session_attributes (no
        # "parameters"); params are in the previous entry.
        if not parameters and tool.name in self.hooks_state.tool_info:
            executions = self.hooks_state.tool_info[tool.name]
            idx = self.hooks_state.tool_info_index.get(tool.name, 0)
            if idx > 0 and idx <= len(executions):
                params_entry = executions[idx - 1]
                parameters = params_entry.get("parameters", [])
        if tool.name == self.knowledge_base_tool or tool.name not in self.hooks_state.agents_names:
            self.hooks_state.advance_tool_info_index(tool.name)

        logger.info(f"[HOOK] Encaminhando para o manager. {result}")

        if tool.name == self.knowledge_base_tool:
            await self._on_tool_end_knowledge_base(context, agent, tool, result, context_data, project_uuid, parameters)
        elif tool.name not in self.hooks_state.agents_names:
            await self._on_tool_end_regular_tool(context, agent, tool, result, context_data, project_uuid, parameters)

    async def on_end(self, context, agent, output):
        logger.info(f"[HOOK] Enviando resposta final {output}.")

        if isinstance(output, FinalResponse):
            final_response = output.final_response
        else:
            final_response = output

        context_data = context.context
        trace_data = {
            "eventTime": pendulum.now().to_iso8601_string(),
            "sessionId": context_data.session.get_session_id(),
            "trace": {
                "orchestrationTrace": {"observation": {"finalResponse": {"text": final_response}, "type": "FINISH"}}
            },
        }
        await self.trace_handler.send_trace(
            context_data, _get_agent_slug(agent, self.hooks_state), "sending_response", trace_data
        )

        if (self.use_components and self.save_components_trace) or not self.use_components:
            await self.trace_handler.save_trace_data(
                trace_events=self.trace_handler.hooks_state.trace_data,
                project_uuid=context_data.project.get("uuid"),
                input_text=context_data.input_text,
                contact_urn=context_data.contact.get("urn"),
                full_response=final_response,
                preview=self.preview,
                session_id=context_data.session.get_session_id(),
                contact_name=context_data.contact.get("name"),
                channel_uuid=context_data.contact.get("channel_uuid"),
            )
