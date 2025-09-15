import json
from typing import Any, Dict, Optional, List

import pendulum
from agents import AgentHooks, RunHooks
from django.conf import settings

from inline_agents.adapter import DataLakeEventAdapter


class HooksState:
    def __init__(self, agents: list):
        self.agents = agents
        self.agents_names = []
        self.lambda_names = {}
        self.tool_calls = {}
        self.trace_data = []

        for agent in self.agents:
            self.agents_names.append(agent.get("agentName"))
            for action_group in agent.get("actionGroups", []):
                action_group_name = action_group.get("actionGroupName")
                function_names = []
                for function_schema in action_group.get("functionSchema", {}).get("functions", []):
                    function_name = function_schema.get("name")
                    function_names.append(function_name)
                self.lambda_names[action_group_name] = {
                    "function_name": function_names[0],
                    "function_arn": action_group.get("actionGroupExecutor", {}).get("lambda")
                }

    def add_tool_call(self, tool_call: Dict[str, Any]):
        self.tool_calls.update(tool_call)

    def get_events(self, result: dict):
        events = result.get("events", {})
        return events


class TraceHandler:
    def __init__(self, event_manager_notify, preview, rationale_switch, language, user_email, session_id, msg_external_id, turn_off_rationale, hooks_state):
        self.event_manager_notify = event_manager_notify
        self.preview = preview
        self.rationale_switch = rationale_switch
        self.language = language
        self.user_email = user_email
        self.session_id = session_id
        self.msg_external_id = msg_external_id
        self.turn_off_rationale = turn_off_rationale
        self.hooks_state = hooks_state

    async def send_trace(self, context_data, agent_name, trace_type, trace_data={}):
        standardized_event = {
            "config": {
                "agentName": agent_name,
                "type": trace_type,
            },
            "trace": trace_data,
        }
        self.hooks_state.trace_data.append(standardized_event)
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
        channel_uuid: str
    ):
        await self.event_manager_notify(
            event='save_inline_trace_events',
            trace_events=trace_events,
            project_uuid=project_uuid,
            user_input=input_text,
            contact_urn=contact_urn,
            agent_response=full_response,
            preview=preview,
            session_id=session_id,
            source_type="agent",  # If user message, source_type="user"
            contact_name=contact_name,
            channel_uuid=channel_uuid
        )

class RunnerHooks(RunHooks):
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
            hooks_state=hooks_state
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

        super().__init__()

    async def on_llm_start(self, context, agent, system_prompt, input_items) -> None:
        print("\033[34m[HOOK] Acionando o modelo.\033[0m")
        context_data = context.context
        await self.trace_handler.send_trace(context_data, agent.name, "invoking_model")

    async def on_llm_end(self, context, agent, response, **kwargs):
        context_data = context.context
        for reasoning_item in response.output:
            if getattr(reasoning_item, "type", None) == "reasoning_item" and hasattr(reasoning_item, "summary") and reasoning_item.summary:
                print("\033[34m[HOOK] Pensando.\033[0m")
                for summary in reasoning_item.summary:
                    summary.text
                    trace_data = {
                        "collaboratorName": "",
                        "eventTime": pendulum.now().to_iso8601_string(),
                        "trace": {
                            "orchestrationTrace": {
                                "rationale": {
                                    "text": summary.text,
                                    "reasoningId": reasoning_item.id
                                }
                            }
                        }
                    }
                    await self.trace_handler.send_trace(context_data, agent.name, "thinking", trace_data)
        print("\033[34m[HOOK] Resposta do modelo recebida.\033[0m")
        await self.trace_handler.send_trace(context_data, agent.name, "model_response_received")


class CollaboratorHooks(AgentHooks):
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
            hooks_state=hooks_state
        )
        self.agent_name = agent_name
        self.data_lake_event_adapter = data_lake_event_adapter
        self.hooks_state = hooks_state
        self.preview = preview

    async def on_start(self, context, agent):
        print(f"\033[34m[HOOK] Atribuindo tarefa ao agente '{agent.name}'.\033[0m")

        context_data = context.context
        await self.trace_handler.send_trace(context_data, agent.name, "delegating_to_agent")
        self.data_lake_event_adapter.to_data_lake_event(
            project_uuid=context_data.project.get("uuid"),
            contact_urn=context_data.contact.get("urn"),
            agent_data={
                "agent_name": agent.name,
                "input_text": context_data.input_text
            }
        )

    async def tool_started(self, context, agent, tool):
        context_data = context.context
        parameters = self.hooks_state.tool_calls.get(tool.name, {})

        print(f"\033[34m[HOOK] Executando ferramenta '{tool.name}'.\033[0m")
        print(f"\033[33m[HOOK] Agente '{agent.name}' vai usar a ferramenta '{tool.name}'.\033[0m")
        trace_data = {
            "collaboratorName": agent.name,
            "eventTime": pendulum.now().to_iso8601_string(),
            "sessionId": context_data.session.get_session_id(),
            "trace": {
                "orchestrationTrace": {
                    "invocationInput": {
                        "actionGroupInvocationInput": {
                            "actionGroupName": tool.name,
                            "executionType": "LAMBDA",
                            "function": tool.name,
                            "parameters": parameters
                        },
                    }
                }
            }
        }
        print("==============tool_calls================")
        print(tool.name)
        print(self.hooks_state.tool_calls)
        print(trace_data)
        print("==========================================")
        await self.trace_handler.send_trace(context_data, agent.name, "executing_tool", trace_data)
        self.data_lake_event_adapter.to_data_lake_event(
            project_uuid=context_data.project.get("uuid"),
            contact_urn=context_data.contact.get("urn"),
            tool_call_data={
                "tool_name": tool.name,
                "parameters": parameters,
                "function_name": self.hooks_state.lambda_names.get(tool.name, {}).get("function_name")
            }
        )

    async def on_tool_end(self, context, agent, tool, result):
        await self.tool_started(context, agent, tool)
        print(f"\033[34m[HOOK] Resultado da ferramenta '{tool.name}' recebido {result}.\033[0m")
        context_data = context.context
        if isinstance(result, str):
            try:
                result_json = json.loads(result)
                events = self.hooks_state.get_events(result_json)
            except Exception:
                events = {}
        elif isinstance(result, dict):
            events = self.hooks_state.get_events(result)

        if events:
            self.data_lake_event_adapter.custom_event_data(
                event_data=events,
                project_uuid=context_data.project.get("uuid"),
                contact_urn=context_data.contact.get("urn"),
                channel_uuid=context_data.contact.get("channel_uuid"),
                agent_name=agent.name,
                preview=self.preview
            )

        trace_data = {
            "collaboratorName": agent.name,
            "eventTime": pendulum.now().to_iso8601_string(),
            "sessionId": context_data.session.get_session_id(),
            "trace": {
                "orchestrationTrace": {
                    "observation": {
                        "actionGroupInvocationOutput": {
                            "metadata": {
                                "result": result
                            },
                            "text": result,
                        },
                    }
                }
            }
        }
        await self.trace_handler.send_trace(context_data, agent.name, "tool_result_received", trace_data)

    async def on_end(self, context, agent, output):
        print(f"\033[34m[HOOK] Enviando resposta ao manager. {output}\033[0m")
        context_data = context.context
        trace_data = {
            "eventTime": pendulum.now().to_iso8601_string(),
            "sessionId": context_data.session.get_session_id(),
            "trace": {
                "orchestrationTrace": {
                    "observation": {
                        "agentCollaboratorInvocationOutput": {
                            "agentCollaboratorName": agent.name,
                            "metadata": {
                                "result": output
                            },
                            "output": {
                                "text": output,
                                "type": "TEXT"
                            }
                        },
                        "type": "AGENT_COLLABORATOR"
                    }
                }
            }
        }
        await self.trace_handler.send_trace(context_data, agent.name, "forwarding_to_manager", trace_data)


class SupervisorHooks(AgentHooks):
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
        **kwargs
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
            hooks_state=hooks_state
        )
        self.agent_name = agent_name
        self.preview = preview
        self.agents = agents
        self.knowledge_base_tool = knowledge_base_tool
        self.data_lake_event_adapter = data_lake_event_adapter
        self.hooks_state = hooks_state
        self.preview = preview

        super().__init__()

    def set_knowledge_base_tool(self, knowledge_base_tool: str):
        self.knowledge_base_tool = knowledge_base_tool

    async def on_start(self, context, agent):
        print(f"\033[34m[HOOK] Agente '{agent.name}' iniciado.\033[0m")

    async def tool_started(self, context, agent, tool):
        context_data = context.context
        parameters = self.hooks_state.tool_calls.get(tool.name, {})
        tool_call_data = {
            "tool_name": tool.name,
            "parameters": parameters
        }

        if tool.name == self.knowledge_base_tool:
            self.data_lake_event_adapter.to_data_lake_event(
                project_uuid=context_data.project.get("uuid"),
                contact_urn=context_data.contact.get("urn"),
                tool_call_data=tool_call_data
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
                                "text": context_data.input_text
                            },
                        }
                    }
                }
            }
            await self.trace_handler.send_trace(context_data, agent.name, "searching_knowledge_base", trace_data)
        elif tool.name not in self.hooks_state.agents_names:
            print(f"\033[34m[HOOK] Agente '{agent.name}' vai usar a ferramenta '{tool.name}'.\033[0m")
            trace_data = {
                "collaboratorName": agent.name,
                "eventTime": pendulum.now().to_iso8601_string(),
                "sessionId": context_data.session.get_session_id(),
                "trace": {
                    "orchestrationTrace": {
                        "invocationInput": {
                            "actionGroupInvocationInput": {
                                "actionGroupName": tool.name,
                                "executionType": "LAMBDA",
                                "function": tool.name,
                                "parameters": parameters
                            },
                        }
                    }
                }
            }
            await self.trace_handler.send_trace(context_data, agent.name, "executing_tool", trace_data)
            self.data_lake_event_adapter.to_data_lake_event(
                project_uuid=context_data.project.get("uuid"),
                contact_urn=context_data.contact.get("urn"),
                tool_call_data={
                    "tool_name": tool.name,
                    "parameters": parameters,
                    "function_name": self.hooks_state.lambda_names.get(tool.name, {}).get("function_name")
                }
            )

    async def on_tool_end(self, context, agent, tool, result):
        # calling tool_started here instead of on_tool_start so we can get the parameters from tool execution
        await self.tool_started(context, agent, tool)
        print(f"\033[34m[HOOK] Encaminhando para o manager. {result}\033[0m")

        context_data = context.context

        if tool.name == self.knowledge_base_tool:
            trace_data = {
                "eventTime": pendulum.now().to_iso8601_string(),
                "sessionId": context_data.session.get_session_id(),
                "trace": {
                    "orchestrationTrace": {
                        "observation": {
                            "knowledgeBaseLookupOutput": {
                                "retrievedReferences": result
                            },
                        }
                    }
                }
            }
            await self.trace_handler.send_trace(context_data, agent.name, "search_result_received", trace_data)
        elif tool.name in self.hooks_state.agents_names:
            if isinstance(result, str):
                try:
                    result_json = json.loads(result)
                    events = self.hooks_state.get_events(result_json)
                except Exception:
                    events = {}
            elif isinstance(result, dict):
                events = self.hooks_state.get_events(result)

            if events:
                self.data_lake_event_adapter.custom_event_data(
                    event_data=events,
                    project_uuid=context_data.project.get("uuid"),
                    contact_urn=context_data.contact.get("urn"),
                    channel_uuid=context_data.contact.get("channel_uuid"),
                    agent_name=agent.name,
                    preview=self.preview
                )

            trace_data = {
                "collaboratorName": agent.name,
                "eventTime": pendulum.now().to_iso8601_string(),
                "sessionId": context_data.session.get_session_id(),
                "trace": {
                    "orchestrationTrace": {
                        "observation": {
                            "actionGroupInvocationOutput": {
                                "metadata": {
                                    "result": result
                                },
                                "text": result,
                            },
                        }
                    }
                }
            }
            await self.trace_handler.send_trace(context_data, agent.name, "tool_result_received", trace_data)

    async def on_end(self, context, agent, output):
        print(f"\033[34m[HOOK] Enviando resposta final {output}.\033[0m")
        context_data = context.context
        trace_data = {
            "eventTime": pendulum.now().to_iso8601_string(),
            "sessionId": context_data.session.get_session_id(),
            "trace": {
                "orchestrationTrace": {
                    "observation": {
                        "finalResponse": {
                            "text": output
                        },
                        "type": "FINISH"
                    }
                }
            }
        }
        await self.trace_handler.send_trace(context_data, agent.name, "sending_response", trace_data)
        await self.trace_handler.save_trace_data(
            trace_events=self.trace_handler.hooks_state.trace_data,
            project_uuid=context_data.project.get("uuid"),
            input_text=context_data.input_text,
            contact_urn=context_data.contact.get("urn"),
            full_response=output,
            preview=self.preview,
            session_id=context_data.session.get_session_id(),
            contact_name=context_data.contact.get("name"),
            channel_uuid=context_data.contact.get("channel_uuid")
        )
