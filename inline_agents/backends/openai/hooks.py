import json
import logging
from typing import TYPE_CHECKING, Dict, List, Optional

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
from django.conf import settings

from inline_agents.adapter import DataLakeEventAdapter
from inline_agents.backends.openai.entities import FinalResponse, HooksState

logger = logging.getLogger(__name__)


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


def get_model_string(model) -> str:
    return model if isinstance(model, str) else model.model


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
        )


class HooksMixin:
    def _safe_parse_json(self, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        return value

    def _process_custom_events(self, context_data, tool_name, result_json, agent_slug):
        project_uuid = context_data.project.get("uuid")
        events = []

        try:
            if isinstance(result_json, (dict, list)):
                events = self.hooks_state.get_events(result_json, tool_name)
        except Exception as e:
            logger.error(f"Error in get_events for tool '{tool_name}': {e}")
            sentry_sdk.set_context(
                "get_events_error",
                {
                    "tool_name": tool_name,
                    "project_uuid": project_uuid,
                    "contact_urn": context_data.contact.get("urn", "unknown"),
                },
            )
            sentry_sdk.capture_exception(e)
            return

        if not events or events == "[]":
            return

        if isinstance(events, str):
            try:
                events = json.loads(events)
            except json.JSONDecodeError as e:
                sentry_sdk.set_context("custom event to data lake", {"event_data": events})
                sentry_sdk.set_tag("project_uuid", project_uuid)
                sentry_sdk.capture_exception(e)
                return

        if isinstance(events, dict):
            events = events.get("events", [])

        if isinstance(events, list) and len(events) > 0:
            logger.info(f"[HOOK] Eventos da ferramenta '{tool_name}': {events}")
            try:
                self.data_lake_event_adapter.custom_event_data(
                    event_data=events,
                    project_uuid=project_uuid,
                    contact_urn=context_data.contact.get("urn"),
                    channel_uuid=context_data.contact.get("channel_uuid"),
                    agent_name=agent_slug,
                    preview=self.preview,
                    conversation=self.conversation,
                )
            except Exception as e:
                logger.error(f"Error calling custom_event_data in SupervisorHooks: {str(e)}")
                sentry_sdk.capture_exception(e)

    def _send_tool_result_datalake(self, context_data, tool_name, result, parameters, agent, function_name=None):
        try:
            result_value = result
            if isinstance(result, str):
                result_value = self._safe_parse_json(result)
            elif isinstance(result, dict):
                result_value = result

            self.data_lake_event_adapter.to_data_lake_event(
                project_uuid=context_data.project.get("uuid"),
                contact_urn=context_data.contact.get("urn"),
                tool_result_data={
                    "tool_name": tool_name,
                    "result": result_value,
                    "parameters": parameters,
                    "function_name": function_name,
                },
                agent_data={"agent_name": agent.name},
                foundation_model=get_model_string(agent.model),
                backend="openai",
                channel_uuid=context_data.contact.get("channel_uuid"),
                conversation=self.conversation,
            )
        except Exception as e:
            logger.error(f"Error sending tool result event for tool '{tool_name}': {str(e)}")
            sentry_sdk.set_context(
                "tool_result_event_error",
                {
                    "tool_name": tool_name,
                    "project_uuid": context_data.project.get("uuid"),
                    "contact_urn": context_data.contact.get("urn", "unknown"),
                },
            )
            sentry_sdk.capture_exception(e)

    async def _handle_knowledge_base_flow(self, context_data, agent, tool, result, parameters):
        agent_slug = _get_agent_slug(agent, self.hooks_state)

        trace_data = {
            "eventTime": pendulum.now().to_iso8601_string(),
            "sessionId": context_data.session.get_session_id(),
            "trace": {
                "orchestrationTrace": {
                    "observation": {
                        "knowledgeBaseLookupOutput": {"retrievedReferences": result},
                    }
                }
            },
        }

        await self.trace_handler.send_trace(context_data, agent.name, "search_result_received", trace_data)

        self._send_tool_result_datalake(context_data, tool.name, result, parameters, agent, function_name=None)

        await self.trace_handler.send_trace(context_data, agent_slug, "search_result_received", trace_data)

    async def _handle_standard_tool_flow(self, context_data, agent, tool, result, parameters):
        agent_slug = _get_agent_slug(agent, self.hooks_state)

        result_json = self._safe_parse_json(result)
        self._process_custom_events(context_data, tool.name, result_json, agent_slug)

        function_name = self.hooks_state.lambda_names.get(tool.name, {}).get("function_name")
        self._send_tool_result_datalake(context_data, tool.name, result, parameters, agent, function_name=function_name)

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

    def _process_events_with_warning(self, context_data, tool_name, result_json, agent_slug):
        """
        Extrai e envia eventos customizados, emitindo um aviso específico
        se a ferramenta for humana/suporte e não retornar eventos.
        """
        project_uuid = context_data.project.get("uuid")
        events = []

        # 1. Tentativa de extração de eventos
        try:
            if isinstance(result_json, (dict, list)):
                events = self.hooks_state.get_events(result_json, tool_name)
        except Exception as e:
            logger.error(f"Error in get_events for tool '{tool_name}': {e}")
            sentry_sdk.set_context(
                "get_events_error",
                {
                    "tool_name": tool_name,
                    "project_uuid": project_uuid,
                    "contact_urn": context_data.contact.get("urn", "unknown"),
                },
            )
            sentry_sdk.capture_exception(e)
            return

        # 2. Normalização da lista de eventos
        if events and events != "[]":
            if isinstance(events, str):
                try:
                    events = json.loads(events)
                except json.JSONDecodeError as e:
                    sentry_sdk.set_context("custom event to data lake", {"event_data": events})
                    sentry_sdk.set_tag("project_uuid", project_uuid)
                    sentry_sdk.capture_exception(e)
                    events = []

            if isinstance(events, dict):
                events = events.get("events", [])
        else:
            events = []

        # 3. Envio ou Aviso (Lógica específica do Collaborator)
        if isinstance(events, list) and len(events) > 0:
            logger.info(f"[HOOK] Eventos da ferramenta '{tool_name}': {events}")
            try:
                self.data_lake_event_adapter.custom_event_data(
                    event_data=events,
                    project_uuid=project_uuid,
                    contact_urn=context_data.contact.get("urn"),
                    channel_uuid=context_data.contact.get("channel_uuid"),
                    agent_name=agent_slug,
                    preview=self.preview,
                    conversation=self.conversation,
                )
            except Exception as e:
                logger.error(f"Error calling custom_event_data in CollaboratorHooks: {str(e)}")
                sentry_sdk.capture_exception(e)
        else:
            # Aviso específico desta classe
            if "human" in tool_name.lower() or "support" in tool_name.lower():
                logger.warning(
                    f"No events found for tool '{tool_name}'. "
                    f"This may result in missing record in contact history. "
                    f"Project: {project_uuid}, Contact: {context_data.contact.get('urn', 'unknown')}"
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

        super().__init__()  # type: ignore

    async def on_llm_start(self, context, agent, system_prompt, input_items) -> None:
        logger.info("[HOOK] Acionando o modelo.")
        context_data = context.context
        await self.trace_handler.send_trace(
            context_data, _get_agent_slug(agent, self.trace_handler.hooks_state), "invoking_model"
        )

    async def on_llm_end(self, context, agent, response, **kwargs):
        context_data = context.context
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
            foundation_model=get_model_string(agent.model),
            backend="openai",
            channel_uuid=context_data.contact.get("channel_uuid"),
            conversation=self.conversation,
        )

    async def tool_started(self, context, agent, tool):
        context_data = context.context
        tool_info = self.hooks_state.get_tool_info(tool.name)
        parameters = tool_info.get("parameters", [])

        agent_slug = _get_agent_slug(agent, self.hooks_state)
        # Update last_active_agent_slug when collaborator executes tools
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
        self.data_lake_event_adapter.to_data_lake_event(
            project_uuid=context_data.project.get("uuid"),
            contact_urn=context_data.contact.get("urn"),
            tool_call_data={
                "tool_name": tool.name,
                "parameters": parameters,
                "function_name": self.hooks_state.lambda_names.get(tool.name, {}).get("function_name"),
            },
            agent_data={"agent_name": agent_slug},  # Pass agent_data for agent_uuid enrichment
            foundation_model=get_model_string(agent.model),
            backend="openai",
            channel_uuid=context_data.contact.get("channel_uuid"),
            conversation=self.conversation,
        )
        self.hooks_state.advance_tool_info_index(tool.name)

    async def on_tool_end(self, context, agent, tool, result):
        await self.tool_started(context, agent, tool)
        logger.info(f"[HOOK] Resultado da ferramenta '{tool.name}' recebido {result}.")

        context_data = context.context
        tool_info = self.hooks_state.get_tool_info(tool.name)
        parameters = tool_info.get("parameters", [])
        agent_slug = _get_agent_slug(agent, self.hooks_state)

        result_json = self._safe_parse_json(result)

        self._process_events_with_warning(context_data, tool.name, result_json, agent_slug)

        function_name = self.hooks_state.lambda_names.get(tool.name, {}).get("function_name")
        self._send_tool_result_datalake(
            context_data=context_data,
            tool_name=tool.name,
            result=result,
            parameters=parameters,
            agent=agent,
            function_name=function_name,
        )

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


class SupervisorHooks(AgentHooks, HooksMixin):  # type: ignore[misc]
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
        tool_call_data = {"tool_name": tool.name, "parameters": parameters}

        if tool.name == self.knowledge_base_tool:
            self.data_lake_event_adapter.to_data_lake_event(
                project_uuid=context_data.project.get("uuid"),
                contact_urn=context_data.contact.get("urn"),
                tool_call_data=tool_call_data,
                agent_data={
                    "agent_name": _get_agent_slug(agent, self.hooks_state)
                },  # Pass agent_data for agent_uuid enrichment
                foundation_model=get_model_string(agent.model),
                backend="openai",
                channel_uuid=context_data.contact.get("channel_uuid"),
                conversation=self.conversation,
            )
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
            self.data_lake_event_adapter.to_data_lake_event(
                project_uuid=context_data.project.get("uuid"),
                contact_urn=context_data.contact.get("urn"),
                tool_call_data={
                    "tool_name": tool.name,
                    "parameters": parameters,
                    "function_name": self.hooks_state.lambda_names.get(tool.name, {}).get("function_name"),
                },
                agent_data={"agent_name": agent_slug},  # Pass agent_data for agent_uuid enrichment
                foundation_model=get_model_string(agent.model),
                backend="openai",
                channel_uuid=context_data.contact.get("channel_uuid"),
                conversation=self.conversation,
            )
            self.hooks_state.advance_tool_info_index(tool.name)

    async def on_tool_end(self, context, agent, tool, result):
        # calling tool_started here instead of on_tool_start so we can get the parameters from tool execution
        await self.tool_started(context, agent, tool)
        logger.info(f"[HOOK] Encaminhando para o manager. {result}")

        context_data = context.context
        tool_info = self.hooks_state.get_tool_info(tool.name)
        parameters = tool_info.get("parameters", [])

        if tool.name == self.knowledge_base_tool:
            await self._handle_knowledge_base_flow(context_data, agent, tool, result, parameters)

        elif tool.name not in self.hooks_state.agents_names:
            await self._handle_standard_tool_flow(context_data, agent, tool, result, parameters)

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
