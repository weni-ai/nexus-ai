
from typing import List
from router.entities import (
    FlowDTO, Message, DBCon, AgentDTO, InstructionDTO, ContentBaseDTO
)

from nexus.intelligences.llms.client import LLMClient
from router.indexer import get_chunks


class Indexer:
    pass

def call_llm(
        indexer: Indexer,
        llm_model: LLMClient,
        message: Message,
        content_base_uuid: str,
        agent: AgentDTO,
        instructions: List[InstructionDTO],
        llm_config
    ) -> str:

    chunks: List[str] = get_chunks(
        indexer,
        text=message.text,
        content_base_uuid=content_base_uuid
    )

    if not chunks:
        raise Exception  # TODO: treat exception
    
    response = llm_model.request_gpt(
        instructions,
        chunks,
        agent.__dict__,
        message.text,
        llm_config,
    )

    gpt_message = response.get("answers")[0].get("text")

    return gpt_message