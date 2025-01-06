
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
from nexus.intelligences.llms.exceptions import TokenLimitError


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

    try:

        print(f"\n\n[+ Message: {message.text} +]\n\n")

        response = llm_model.request_gpt(
            instructions=instructions,
            chunks=chunks,
            agent=agent.__dict__,
            question=message.text,
            llm_config=llm_config,
            last_messages=last_messages
        )
    except TokenLimitError:
        llm_model = list(LLMClient.get_by_type("chatgpt"))[0](
            model_version="gpt-4o-mini",
            api_key=settings.OPENAI_API_KEY
        )
        llm_model.request_gpt(
            instructions=instructions,
            chunks=chunks,
            agent=agent.__dict__,
            question=message.text,
            llm_config=llm_config,
            last_messages=last_messages
        )

    gpt_message = response.get("answers")[0].get("text")

    return gpt_message
