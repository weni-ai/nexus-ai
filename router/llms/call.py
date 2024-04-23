
from typing import List
from router.entities import (
    Message, AgentDTO, InstructionDTO, LLMSetupDTO
)

from nexus.intelligences.llms.client import LLMClient
from router.indexer import get_chunks


class Indexer:
    pass

def call_llm(
        chunks: List[str],
        llm_model: LLMClient,
        message: Message,
        agent: AgentDTO,
        instructions: List[InstructionDTO],
        llm_config: LLMSetupDTO
    ) -> str:

    response = llm_model.request_gpt(
        instructions,
        chunks,
        agent.__dict__,
        message.text,
        llm_config,
    )

    gpt_message = response.get("answers")[0].get("text")

    return gpt_message