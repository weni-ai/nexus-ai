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


@dataclass
class LLMSetupDTO:
    model: str
    model_version: str
    temperature: str
    top_p: str
    top_k: str = None
    token: str = None
    max_length: str = None
    max_tokens: str = None
