import os

from typing import List, Dict
from django.conf import settings

from router.repositories.orm import FlowsORMRepository, ContentBaseORMRepository
from router.repositories import Repository
from router.classifiers.zeroshot import ZeroshotClassifier
from router.classifiers import Classifier
from router.classifiers import classify
from router.entities import (
    FlowDTO, Message, AgentDTO, InstructionDTO, ContentBaseDTO, LLMSetupDTO
)
from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase

from nexus.event_driven.signals import message_started, message_finished

from router.direct_message import DirectMessage
from router.flow_start import FlowStart
from nexus.intelligences.llms.client import LLMClient

from router.dispatcher import dispatch

from router.indexer import get_chunks
from router.llms.call import call_llm, Indexer
from nexus.usecases.logs.entities import LogMetadata


def route(
        classification: str,
        message: Message,
        content_base_repository: Repository,
        flows_repository: Repository,
        indexer: Indexer,
        llm_client: LLMClient,
        direct_message: DirectMessage,
        flow_start: FlowStart,
        llm_config: LLMSetupDTO,
        flows_user_email: str,
        log_usecase,
    ):
    try:
        if classification == Classifier.CLASSIFICATION_OTHER:
            print(f"[- Fallback -]")

            fallback_flow: FlowDTO = flows_repository.project_flow_fallback(message.project_uuid, True)

            content_base: ContentBaseDTO = content_base_repository.get_content_base_by_project(message.project_uuid)

            agent: AgentDTO = content_base_repository.get_agent(content_base.uuid)
            agent = agent.set_default_if_null()

            instructions: List[InstructionDTO] = content_base_repository.list_instructions(content_base.uuid)        
            instructions: List[str] = [instruction.instruction for instruction in instructions]

            if instructions == []:
                instructions += settings.DEFAULT_INSTRUCTIONS
            
            instructions.append(settings.LLM_DEFAULT_CHAR_INSTRUCTION)
            chunks: List[str] = get_chunks(
                indexer,
                text=message.text,
                content_base_uuid=content_base.uuid
            )

            print(f"[+ Contexto do Sentenx: {chunks} +]")

            llm_response: str = call_llm(
                chunks=chunks,
                llm_model=llm_client,
                message=message,
                agent=agent,
                instructions=instructions,
                llm_config=llm_config,
            )

            print("=============LLM===================")
            print(f"[+ Resposta do LLM: {llm_response}+]")
            print("===================================")

            llm_response = llm_response[:settings.LLM_CHAR_LIMIT]

            metadata = LogMetadata(
                agent_name=agent.name,
                agent_role=agent.role,
                agent_personality=agent.personality,
                agent_goal=agent.goal,
                instructions=instructions
            )
            log_usecase.update_log_field(
                chunks=chunks,
                prompt=llm_client.prompt,
                project_id=message.project_uuid,
                content_base_id=content_base.uuid,
                classification=classification,
                llm_model=llm_config.model,
                llm_response=llm_response,
                metadata=metadata.dict
            )

            if fallback_flow:
                dispatch(
                    message=message,
                    flow=fallback_flow.uuid,
                    flow_start=flow_start,
                    llm_response=llm_response,
                    user_email=flows_user_email
                )
                return

            dispatch(
                llm_response=llm_response,
                message=message,
                direct_message=direct_message,
                user_email=flows_user_email
            )
            return

        flow: FlowDTO = flows_repository.get_project_flow_by_name(message.project_uuid, classification)

        dispatch(
            message=message,
            flow_start=flow_start,
            flow=flow.uuid,
            user_email=flows_user_email
        )
    except Exception as e:
        log_usecase.update_status("F", exception_text=e)
