import pendulum
from agents import RunHooks, AgentHooks
from django.conf import settings



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
    ):
        self.agents = agents
        self.supervisor_name = supervisor_name
        self.rationale_switch = rationale_switch
        self.language = language
        self.user_email = user_email
        self.session_id = session_id
        self.msg_external_id = msg_external_id
        self.turn_off_rationale = turn_off_rationale
        self.preview = preview
        self.list_tools_called = []
        self.list_handoffs_requested = []
        self.event_manager_notify = event_manager_notify
        self.agents_names = []
        self.knowledge_base_tool = None
        self.current_agent = None

        for agent in self.agents:
            self.agents_names.append(agent.get("agentName"))

        super().__init__()

    async def on_llm_start(self, context, agent, system_prompt, input_items, **kwargs):
        print("---------------------ON LLM START---------------------")
        print(f"Context: {context}")
        print(f"Agent: {agent}")
        print(f"System Prompt: {system_prompt}")
        print(f"Input Items: {input_items}")
        print(f"Kwargs: {kwargs}")
        print("--------------------------------")

    async def on_llm_end(self, context, agent, response, **kwargs):
        print("---------------------ON LLM ENDS---------------------")
        print(f"Response: {context}")
        print(f"Response: {agent}")
        print(f"Response: {response}")
        print(f"Kwargs: {kwargs}")
        agent_name = self.current_agent if self.current_agent else agent.name
        await self.send_trace(context, agent_name, "model_response_received", response)
        print("--------------------------------")

class SupervisorHooks(AgentHooks):
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
    ):
        self.agents = agents
        self.supervisor_name = supervisor_name
        self.rationale_switch = rationale_switch
        self.language = language
        self.user_email = user_email
        self.session_id = session_id
        self.msg_external_id = msg_external_id
        self.turn_off_rationale = turn_off_rationale
        self.preview = preview
        self.list_tools_called = []
        self.list_handoffs_requested = []
        self.event_manager_notify = event_manager_notify
        self.agents_names = []
        self.knowledge_base_tool = None
        self.current_agent = None

        for agent in self.agents:
            self.agents_names.append(agent.get("agentName"))

        super().__init__()

    def set_knowledge_base_tool(self, knowledge_base_tool):
        self.knowledge_base_tool = knowledge_base_tool

    async def send_trace(self, context_data, agent_name, trace_type, trace_data={}):
        standardized_event = {
            "config": {
                "agentName": agent_name,
                "type": trace_type,
            },
            "trace": trace_data,
        }
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

    async def on_start(self, context, agent):
        context_data = context.context
        await self.send_trace(context_data, agent.name, "invoking_model")
        print(f"\033[34m[HOOK] Agente '{agent.name}' iniciado.\033[0m")

    async def on_tool_start(self, context, agent, tool):
        context_data = context.context
        self.list_tools_called.append(tool.name)

        if tool.name == self.knowledge_base_tool:
            print(f"\033[33m[HOOK] Agente '{agent.name}' vai usar a ferramenta '{tool.name}'.\033[0m")
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
            await self.send_trace(context_data, agent.name, "searching_knowledge_base", trace_data)

        if tool.name in self.agents_names:
            print(f"\033[33m[HOOK] Agente '{agent.name}' vai usar o agente '{tool.name}'.\033[0m")
            self.current_agent = tool.name
            await self.send_trace(context_data, agent.name, "delegating_to_agent")

        else:
            print(f"\033[33m[HOOK] Agente '{agent.name}' vai usar a ferramenta '{tool.name}'.\033[0m")
            trace_data = {
                "collaboratorName": self.current_agent if self.current_agent else agent.name,
                "eventTime": pendulum.now().to_iso8601_string(),
                "sessionId": context_data.session.get_session_id(),
                "trace": {
                    "orchestrationTrace": {
                        "invocationInput": {
                            "actionGroupInvocationInput": {
                                "actionGroupName": tool.name,
                                "executionType": "LAMBDA",
                                "function": tool.name,
                                "parameters": tool.params_json_schema
                            },
                        }
                    }
                }
            }
            await self.send_trace(context_data, agent.name, "executing_tool", trace_data)

    async def on_tool_end(self, context, agent, tool, result):
        context_data = context.context
        if tool.name == self.knowledge_base_tool:
            print(f"\033[33m[HOOK] Agente '{agent.name}' terminou de usar a ferramenta '{tool.name}'.\033[0m")
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
            await self.send_trace(context_data, agent.name, "search_result_received", trace_data)

        if tool.name in self.agents_names:
            print(f"\033[33m[HOOK] Agente '{agent.name}' terminou de usar o agente '{tool.name}'.\033[0m")
            trace_data = {
                "eventTime": pendulum.now().to_iso8601_string(),
                "sessionId": context_data.session.get_session_id(),
                "trace": {
                    "orchestrationTrace": {
                        "observation": {
                            "agentCollaboratorInvocationOutput": {
                                "agentCollaboratorName": self.current_agent,
                                "metadata": {
                                    "result": result
                                },
                                "output": {
                                    "text": result,
                                    "type": "TEXT"
                                }
                            },
                            "type": "AGENT_COLLABORATOR"
                        }
                    }
                }
            }
            await self.send_trace(context_data, self.current_agent, "forwarding_to_manager", trace_data)
            self.current_agent = None

        else:
            print(f"\033[31m[HOOK] Agente '{agent.name}' terminou de usar a ferramenta '{tool.name}'.\033[0m")
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
            await self.send_trace(context_data, agent.name, "tool_result_received", trace_data)

    async def on_end(self, context, agent, output):
        context_data = context.context
        print(f"\033[32m[HOOK] Agente '{agent.name}' finalizou.\033[0m")
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
        await self.send_trace(context_data, agent.name, "sending_response", trace_data)
