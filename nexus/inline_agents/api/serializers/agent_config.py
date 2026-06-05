import re

from rest_framework import serializers

from nexus.inline_agents.api.serializers import inline_agent_list_display_name
from nexus.inline_agents.models import IntegratedAgent


def pascal_case_to_kebab(name: str) -> str:
    if not name:
        return ""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1-\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s1).lower()


def format_tool_parameters(raw_params) -> list[dict]:
    if not raw_params:
        return []

    normalized: dict = {}
    if isinstance(raw_params, list):
        for param_dict in raw_params:
            if isinstance(param_dict, dict):
                for param_name, param_meta in param_dict.items():
                    if isinstance(param_meta, dict):
                        normalized[param_name] = param_meta
    elif isinstance(raw_params, dict):
        normalized = raw_params

    return [
        {
            "name": param_name,
            "type": param_meta.get("type", "string"),
            "description": param_meta.get("description", ""),
        }
        for param_name, param_meta in normalized.items()
        if isinstance(param_meta, dict)
    ]


def format_tools_from_skills(skills: list) -> list[dict]:
    tools = []
    for skill in skills or []:
        description = skill.get("description") or ""
        tool_name = pascal_case_to_kebab(skill.get("actionGroupName") or "")

        parameters = []
        for func in skill.get("functionSchema", {}).get("functions", []):
            parameters.extend(format_tool_parameters(func.get("parameters")))

        tools.append(
            {
                "name": tool_name,
                "description": description,
                "parameters": parameters,
            }
        )
    return tools


class AgentConfigSerializer(serializers.Serializer):
    """Serializes active integrated agents into name/description/instructions/tools payload."""

    def to_representation(self, integrated_agent: IntegratedAgent) -> dict:
        agent = integrated_agent.agent
        instruction_text = (agent.instruction or "").strip()
        instructions = [{"instruction": instruction_text}] if instruction_text else []

        skills = []
        if agent.current_version:
            skills = agent.current_version.skills or []

        return {
            "name": inline_agent_list_display_name(agent),
            "description": agent.collaboration_instructions or "",
            "instructions": instructions,
            "tools": format_tools_from_skills(skills),
        }
