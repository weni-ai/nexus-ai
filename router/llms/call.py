
from typing import List
from router.entities import (
    AgentDTO,
    ContactMessageDTO,
    InstructionDTO,
    LLMSetupDTO,
    Message,
)

from django.conf import settings

from nexus.intelligences.llms.client import LLMClient
from nexus.intelligences.llms.wenigpt import WeniGPTClient


class Indexer:
    pass


def call_llm(
    chunks: List[str],
    llm_model: LLMClient,
    message: Message,
    agent: AgentDTO,
    instructions: List[InstructionDTO],
    llm_config: LLMSetupDTO,
    last_messages: List[ContactMessageDTO]
) -> str:

    response = llm_model.request_gpt(
        instructions=instructions,
        chunks=chunks,
        agent=agent.__dict__,
        question=message.text,
        llm_config=llm_config,
        last_messages=last_messages
    )

    gpt_message = response.get("answers")[0].get("text")

    if settings.REFLECTION_ENABLED:

        if llm_model != WeniGPTClient:
            return gpt_message

        llm_model = WeniGPTClient(model_version=settings.REFLECTION_MODEL)
        response = llm_model.request_gpt(
            instructions=instructions,
            chunks=chunks,
            agent=agent.__dict__,
            question=message.text,
            llm_config=llm_config,
            last_messages=last_messages,
            reflection=True
        )

        gpt_message = response.get("answers")[0].get("text")

    return gpt_message
