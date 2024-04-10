from dataclasses import dataclass, fields
from django.conf import settings


@dataclass
class AgentDTO:
    default_fields = {
        "name": settings.DEFAULT_AGENT_NAME,
        "role": settings.DEFAULT_AGENT_ROLE,
        "personality": settings.DEFAULT_AGENT_PERSONALITY,
        "goal": settings.DEFAULT_AGENT_GOAL,
    }
    name: str
    role: str
    personality: str
    goal: str
    content_base_uuid: str
    
    def set_default_if_null(self):
        for field in fields(self):
            field_value = getattr(self, field.name)
            if not field_value:
                setattr(self, field.name, self.default_fields.get(field.name))
        return self


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
