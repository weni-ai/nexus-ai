import os

from typing import List, Dict
from django.conf import settings
from ftfy import fix_encoding

from nexus.intelligences.llms.client import LLMClient
from nexus.usecases.logs.entities import LogMetadata
from router.classifiers.reflection import run_reflection_task

from router.dispatcher import dispatch
from router.indexer import get_chunks
from router.llms.call import call_llm, Indexer
from router.direct_message import DirectMessage
from router.flow_start import FlowStart
from router.repositories import Repository
from router.classifiers import Classifier
from router.entities import (
    AgentDTO,
    ContactMessageDTO,
    ContentBaseDTO,
    InstructionDTO,
    FlowDTO,
    LLMSetupDTO,
    Message,
)


def get_language_codes(language_code: str):
    language_codes = {
        "pt": "português",
        "pt-br": "português",
        "por": "português",
        "en": "inglês",
        "eng": "inglês",
        "es": "espanhol",
        "spa": "espanhol",
    }
    return language_codes.get(language_code, "português")


def bad_words_filter(text: str):
    bad_words_list = os.environ.get("BAD_WORDS_LIST", "").split(",")

    for word in bad_words_list:
        if word in text:
            return os.environ.get("BAD_WORDS_RESPONSE")

    return text


def route(
    classification: str,
    message: Message,
    content_base_repository: Repository,
    flows_repository: Repository,
    message_logs_repository: Repository,
    indexer: Indexer,
    llm_client: LLMClient,
    direct_message: DirectMessage,
    flow_start: FlowStart,
    llm_config: LLMSetupDTO,
    flows_user_email: str,
    log_usecase,
    message_log=None
):
    try:
        content_base: ContentBaseDTO = content_base_repository.get_content_base_by_project(message.project_uuid)

        flow = ""
        if classification != Classifier.CLASSIFICATION_OTHER:
            flow: FlowDTO = flows_repository.get_project_flow_by_name(name=classification)

        if not flow or flow.send_to_llm:

            print("[ + Fallback + ]")

            fallback_flow: FlowDTO = flows_repository.project_flow_fallback(fallback=True)

            if settings.USE_REDIS_CACHE_CONTEXT:
                last_messages: List[ContactMessageDTO] = message_logs_repository.list_cached_messages(message.project_uuid, message.contact_urn)
            else:
                last_messages: List[ContactMessageDTO] = message_logs_repository.list_last_messages(message.project_uuid, message.contact_urn, 5)

            agent: AgentDTO = content_base_repository.get_agent(content_base.uuid)
            agent = agent.set_default_if_null()

            instructions: List[InstructionDTO] = content_base_repository.list_instructions(content_base.uuid)
            instructions: List[str] = [instruction.instruction for instruction in instructions]

            if instructions == []:
                instructions += settings.DEFAULT_INSTRUCTIONS

            full_chunks: List[Dict] = get_chunks(
                indexer,
                text=message.text,
                content_base_uuid=content_base.uuid
            )

            print(f"[+ Instructions: {instructions} +]")

            chunks: List[str] = []
            for chunk in full_chunks:
                full_page = chunk.get("full_page").replace("\x00", "\uFFFD")
                try:
                    full_page.encode("latin-1")
                    chunks.append(full_page)
                except UnicodeEncodeError:
                    full_page = fix_encoding(full_page)
                    chunks.append(full_page)

                chunk["full_page"] = full_page

            print(f"[ + Chunks: {chunks} + ]")

            llm_response: str = call_llm(
                chunks=chunks,
                llm_model=llm_client,
                message=message,
                agent=agent,
                instructions=instructions,
                llm_config=llm_config,
                last_messages=last_messages,
            )

            llm_response = bad_words_filter(llm_response)

            print(f"[+ LLM Response: {llm_response} +]")

            if message_log:
                run_reflection_task.delay(
                    chunks_used=chunks,
                    llm_response=llm_response,
                    message_log_id=message_log.id,
                )

            metadata = LogMetadata(
                agent_name=agent.name,
                agent_role=agent.role,
                agent_personality=agent.personality,
                agent_goal=agent.goal,
                instructions=instructions
            )
            log_usecase.update_log_field(
                chunks_json=full_chunks,
                chunks=chunks,
                prompt=llm_client.prompt,
                project_id=message.project_uuid,
                content_base_id=content_base.uuid,
                classification=classification,
                llm_model=f"{llm_config.model}:{llm_config.model_version}",
                llm_response=llm_response,
                metadata=metadata.dict
            )

            if fallback_flow:
                log_usecase.send_message()
                return dispatch(
                    message=message,
                    flow=fallback_flow,
                    flow_start=flow_start,
                    llm_response=llm_response,
                    user_email=flows_user_email
                )

            if not flow:
                log_usecase.send_message()
                return dispatch(
                    llm_response=llm_response,
                    message=message,
                    direct_message=direct_message,
                    user_email=flows_user_email,
                    full_chunks=full_chunks,
                )

            # Actions with send_to_llm=True
            log_usecase.update_log_field(
                reflection_data={
                    "tag": "action_started",
                    "action_uuid": str(flow.pk),
                    "action_name": flow.name,
                }
            )
            log_usecase.send_message()
            return dispatch(
                message=message,
                flow=flow,
                flow_start=flow_start,
                llm_response=llm_response,
                user_email=flows_user_email
            )

        log_usecase.update_log_field(
            project_id=message.project_uuid,
            content_base_id=content_base.uuid,
            classification=classification,
            reflection_data={
                "tag": "action_started",
                "action_uuid": str(flow.pk),
                "action_name": flow.name,
            }
        )

        return dispatch(
            message=message,
            flow_start=flow_start,
            flow=flow,
            user_email=flows_user_email
        )

    except Exception as e:
        log_usecase.update_status("F", exception_text=e)
        raise e
