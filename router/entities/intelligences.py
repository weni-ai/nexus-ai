from dataclasses import dataclass


@dataclass
class AgentDTO:
    name: str
    role: str
    personality: str
    goal: str
    content_base_uuid: str


@dataclass
class InstructionDTO:
    instruction: str
    content_base_uuid: str


@dataclass
class LLMConfigDTO:
    pass
