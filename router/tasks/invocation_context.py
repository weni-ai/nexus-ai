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

        return cls(
            project_dict=project_dict,
            content_base_dict=content_base_dict,
            team=team,
            guardrails_config=guardrails_config,
            inline_agent_config_dict=inline_agent_config_dict,
            instructions=instructions,
            agent_data=agent_data,
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
            "supervisor_uuid": self.project_dict.get("supervisor_uuid"),
            "instructions": self.instructions,
            "agent_data": self.agent_data,
            "guardrails_config": self.guardrails_config,
            "default_instructions_for_collaborators": (
                self.inline_agent_config_dict.get("default_instructions_for_collaborators")
                if self.inline_agent_config_dict
                else None
            ),
        }
