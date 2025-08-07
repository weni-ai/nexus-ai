from agents import AgentHooks

class HooksDefault(AgentHooks):
        list_tools_called = []
        list_handoffs_requested = []
        
        async def on_start(self, context, agent):
            print(f"\033[34m[HOOK] Agente '{agent.name}' iniciado.\033[0m")
            # print(f"\033[36m[HOOK] Context: {context}\033[0m")

        async def on_end(self, context, agent, output):
            print(f"\033[32m[HOOK] Agente '{agent.name}' finalizou.\033[0m")

        async def on_handoff(self, context, agent, source):
            # print(f"\033[35m[HOOK] Handoff recebido pelo agente '{agent.name}' do agente '{source.name}'.\033[0m")
            self.list_handoffs_requested.append(source.name)
        async def on_tool_start(self, context, agent, tool):
            self.list_tools_called.append(tool.name)
            print(f"\033[33m[HOOK] Agente '{agent.name}' vai usar a ferramenta '{tool.name}'.\033[0m")
            # print(f"\033[33m[HOOK] Tool: {tool}\033[0m")

        async def on_tool_end(self, context, agent, tool, result):
            # print(f"\033[31m[HOOK] Agente '{agent.name}' terminou de usar a ferramenta '{tool.name}'.\033[0m")
            print(f"\033[31m[HOOK] Resultado: {result}\033[0m")