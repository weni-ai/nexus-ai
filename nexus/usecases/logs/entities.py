from dataclasses import dataclass
from typing import Dict, List


@dataclass
class LogMetadata:
    agent_name: str
    agent_role: str
    agent_personality: str
    agent_goal: str
    instructions: List

    @property
    def dict(self) -> Dict:
        return {
            "agent": {
                "name": self.agent_name,
                "role": self.agent_role,
                "personality": self.agent_personality,
                "goal": self.agent_goal,
            },
            "instructions": self.instructions,
        }
