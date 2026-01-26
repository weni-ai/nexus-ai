from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from agents import Session
from pydantic import BaseModel, Field


class HooksState:
    def __init__(self, agents: list):
        self.agents = agents
        self.agents_names = []
        self.lambda_names = {}
        self.tool_calls = {}
        self.trace_data = []
        self.tool_info = {}
        self.tool_info_index = {}
        self.last_active_agent_slug = None  # Track the last agent that executed before formatter

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
                    "function_arn": action_group.get("actionGroupExecutor", {}).get("lambda"),
                }

    def add_tool_info(self, tool_name: str, info: Dict[str, Any]):
        if tool_name not in self.tool_info:
            self.tool_info[tool_name] = []
            self.tool_info_index[tool_name] = 0
        self.tool_info[tool_name].append(info)

    def get_tool_info(self, tool_name: str) -> Dict[str, Any]:
        if tool_name not in self.tool_info:
            return {}

        executions = self.tool_info[tool_name]
        if not executions:
            return {}

        index = self.tool_info_index.get(tool_name, 0)
        if index < len(executions):
            return executions[index]
        return executions[-1] if executions else {}

    def advance_tool_info_index(self, tool_name: str):
        if tool_name in self.tool_info_index:
            max_index = len(self.tool_info.get(tool_name, []))
            if self.tool_info_index[tool_name] < max_index:
                self.tool_info_index[tool_name] += 1

    def add_tool_call(self, tool_call: Dict[str, Any]):
        self.tool_calls.update(tool_call)

    def get_events(self, result: dict, tool_name: str):
        current_info = self.get_tool_info(tool_name)
        session_events = current_info.get("events", {})

        if session_events:
            return session_events

        if isinstance(result, list):
            events = []
            for item in result:
                if isinstance(item, dict):
                    events.extend(item.get("events", {}))
            return events

        events = result.get("events", {})
        return events


@dataclass
class Context:
    input_text: str
    credentials: dict
    globals: dict
    contact: dict
    project: dict
    content_base: dict
    session: "Session"
    hooks_state: HooksState
    constants: dict = field(default_factory=dict)


class FinalResponse(BaseModel):
    """Modelo para a resposta final formatada"""

    final_response: str = Field(description="O resultado final da resposta que ira ser formatado")
