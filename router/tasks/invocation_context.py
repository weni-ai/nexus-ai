"""
Context objects for backend invocation to reduce parameter passing complexity.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class CachedProjectData:
    """Cached project data to avoid database queries."""

    project_dict: Dict
    content_base_dict: Dict
    team: List[Dict]
    guardrails_config: Dict
    inline_agent_config_dict: Optional[Dict]
    instructions: List[str]
    agent_data: Optional[Dict]
    formatter_agent_configurations: Optional[Dict]

    @classmethod
    def from_pre_generation_data(
        cls,
        project_dict: Dict,
        content_base_dict: Dict,
        team: List[Dict],
        guardrails_config: Dict,
        inline_agent_config_dict: Optional[Dict],
        instructions: List[str],
        agent_data: Optional[Dict],
    ) -> "CachedProjectData":
        """Create CachedProjectData from pre-generation service output."""
        # Construct formatter_agent_configurations from cached project_dict
        formatter_agent_configurations = None
        if project_dict.get("default_formatter_foundation_model") or project_dict.get("formatter_instructions"):
            formatter_agent_configurations = {
                "formatter_foundation_model": project_dict.get("default_formatter_foundation_model"),
                "formatter_instructions": project_dict.get("formatter_instructions"),
                "formatter_reasoning_effort": project_dict.get("formatter_reasoning_effort"),
                "formatter_reasoning_summary": project_dict.get("formatter_reasoning_summary"),
                "formatter_send_only_assistant_message": project_dict.get("formatter_send_only_assistant_message"),
                "formatter_tools_descriptions": project_dict.get("formatter_tools_descriptions"),
            }

        return cls(
            project_dict=project_dict,
            content_base_dict=content_base_dict,
            team=team,
            guardrails_config=guardrails_config,
            inline_agent_config_dict=inline_agent_config_dict,
            instructions=instructions,
            agent_data=agent_data,
            formatter_agent_configurations=formatter_agent_configurations,
        )

    def get_invoke_kwargs(self, team: List[Dict]) -> Dict:
        """Get all kwargs for backend.invoke_agents() call, including team data."""
        return {
            "team": team,
            "use_components": self.project_dict.get("use_components", False),
            "rationale_switch": self.project_dict.get("rationale_switch", False),
            "use_prompt_creation_configurations": self.project_dict.get("use_prompt_creation_configurations", False),
            "conversation_turns_to_include": self.project_dict.get("conversation_turns_to_include", 10),
            "exclude_previous_thinking_steps": self.project_dict.get("exclude_previous_thinking_steps", True),
            "human_support": self.project_dict.get("human_support", False),
            "default_supervisor_foundation_model": self.project_dict.get("default_supervisor_foundation_model"),
            "content_base_uuid": self.content_base_dict.get("uuid"),
            "business_rules": self.project_dict.get("human_support_prompt"),
            "instructions": self.instructions,
            "agent_data": self.agent_data,
            "formatter_agent_configurations": self.formatter_agent_configurations,
            "guardrails_config": self.guardrails_config,
            "default_instructions_for_collaborators": (
                self.inline_agent_config_dict.get("default_instructions_for_collaborators")
                if self.inline_agent_config_dict
                else None
            ),
        }
