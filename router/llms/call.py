import logging
from typing import List

from django.conf import settings

from nexus.intelligences.llms.client import LLMClient
from nexus.intelligences.llms.exceptions import TokenLimitError
from router.entities import (
    AgentDTO,
    ContactMessageDTO,
    InstructionDTO,
    LLMSetupDTO,
    Message,
)


class Indexer:
    pass


def call_llm(
    chunks: List[str],
    llm_model: LLMClient,
    message: Message,
    agent: AgentDTO,
    instructions: List[InstructionDTO],
    llm_config: LLMSetupDTO,
    last_messages: List[ContactMessageDTO],
    project_uuid: str = "",
) -> str:
    try:
        logger = logging.getLogger(__name__)
        logger.debug("LLM call message", extra={"text_len": len(message.text) if getattr(message, "text", None) else 0})

        response = llm_model.request_gpt(
            instructions=instructions,
            chunks=chunks,
            agent=agent.__dict__,
            question=message.text,
            llm_config=llm_config,
            last_messages=last_messages,
            project_uuid=project_uuid,
        )
    except TokenLimitError:
        model_version = "gpt-4o-mini"
        llm_config.model_version = model_version
        llm_model = list(LLMClient.get_by_type("chatgpt"))[0](
            model_version=model_version, api_key=settings.OPENAI_API_KEY
        )

        response = llm_model.request_gpt(
            instructions=instructions,
            chunks=chunks,
            agent=agent.__dict__,
            question=message.text,
            llm_config=llm_config,
            last_messages=last_messages,
        )

    gpt_message = response.get("answers")[0].get("text")

    return gpt_message
