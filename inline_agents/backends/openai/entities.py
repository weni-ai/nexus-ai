from dataclasses import dataclass
from typing import Any, Dict

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
        try:
            self.tool_info[tool_name].update(info)
        except KeyError:
            self.tool_info[tool_name] = info

    def add_tool_call(self, tool_call: Dict[str, Any]):
        self.tool_calls.update(tool_call)

    def get_events(self, result: dict, tool_name: str):
        tool_data = self.tool_info.get(tool_name, {})
        if isinstance(tool_data, dict):
            session_events = tool_data.get("events", [])
            if session_events:
                return session_events
        
        for _stored_tool_name, stored_tool_data in self.tool_info.items():
            if isinstance(stored_tool_data, dict) and "events" in stored_tool_data:
                events_list = stored_tool_data.get("events", [])
                if events_list:
                    return events_list
        
        events = result.get("events", [])
        return events


@dataclass
class Context:
    input_text: str
    credentials: dict
    globals: dict
    contact: dict
    project: dict
    content_base: dict
    session: Session
    hooks_state: HooksState


class FinalResponse(BaseModel):
    """Modelo para a resposta final formatada"""

    final_response: str = Field(description="O resultado final da resposta que ira ser formatado")
