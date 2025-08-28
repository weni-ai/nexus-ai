from agents import AgentHooks


class HooksDefault(AgentHooks):
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
    ):
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
        super().__init__()

    async def on_start(self, context, agent):
        context_data = context.context
        standardized_event = {
            "type": "trace_update",
            "trace": {
                "config": {
                    "agentName": agent.name,
                    "type": "invoking_model",
                },
                "trace": {}
            }
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
            channel_uuid=context_data.contact.get("channel_uuid")
        )
        print(f"\033[34m[HOOK] Agente '{agent.name}' iniciado.\033[0m")

    async def on_end(self, context, agent, output):
        # print("=====================on_end===========================")
        print(f"\033[32m[HOOK] Agente '{agent.name}' finalizou.\033[0m")
        # print(f"\033[36m[HOOK] Context: {context}\033[0m")
        # print(f"\033[36m[HOOK] Output: {output}\033[0m")
        # print("================================================")

    async def on_handoff(self, context, agent, source):
        # print("=====================on_handoff===========================")
        print(f"\033[35m[HOOK] Handoff recebido pelo agente '{agent.name}' do agente '{source.name}'.\033[0m")
        self.list_handoffs_requested.append(source.name)
        # print(f"\033[36m[HOOK] Context: {context}\033[0m")
        # print(f"\033[36m[HOOK] Agent: {agent}\033[0m")
        # print(f"\033[36m[HOOK] Source: {source}\033[0m")
        # print("================================================")

    async def on_tool_start(self, context, agent, tool):
        # print("=====================on_tool_start===========================")
        self.list_tools_called.append(tool.name)
        print(f"\033[33m[HOOK] Agente '{agent.name}' vai usar a ferramenta '{tool.name}'.\033[0m")
        # print(f"\033[33m[HOOK] Tool: {tool}\033[0m")
        # print(f"\033[36m[HOOK] Context: {context}\033[0m")
        # print("================================================")

    async def on_tool_end(self, context, agent, tool, result):
        # sprint("======================on_tool_end==========================")
        print(f"\033[31m[HOOK] Agente '{agent.name}' terminou de usar a ferramenta '{tool.name}'.\033[0m")
        print(f"\033[31m[HOOK] Resultado: {result}\033[0m")
        # print(f"\033[36m[HOOK] Context: {context}\033[0m")
        # print(f"\033[36m[HOOK] Agent: {agent}\033[0m")
        # print(f"\033[36m[HOOK] Tool: {tool}\033[0m")
        # print("================================================")
