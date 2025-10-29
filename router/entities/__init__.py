from router.entities.db import DBCon
from router.entities.flow import FlowDTO
from router.entities.intelligences import AgentDTO, InstructionDTO, LLMConfigDTO, LLMSetupDTO
from router.entities.logs import ContactMessageDTO
from router.entities.mailroom import ContactField, Message, message_factory
from router.entities.projects import ProjectDTO

# Re-export from nexus for backwards compatibility
from nexus.usecases.intelligences.intelligences_dto import ContentBaseDTO

__all__ = [
    "AgentDTO",
    "ContactField",
    "ContactMessageDTO",
    "ContentBaseDTO",
    "DBCon",
    "FlowDTO",
    "InstructionDTO",
    "LLMConfigDTO",
    "LLMSetupDTO",
    "Message",
    "ProjectDTO",
    "message_factory",
]
