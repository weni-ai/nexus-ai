
import os
from typing import List, Dict

from fastapi import FastAPI

from router.repositories.orm import FlowsORMRepository, ContentBaseORMRepository
from router.repositories import Repository
from router.classifiers.zeroshot import ZeroshotClassifier
from router.classifiers import Classifier
from router.classifiers import classify
from router.entities import (
    FlowDTO, Message, DBCon, AgentDTO, InstructionDTO, ContentBaseDTO
)
from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase

from nexus.event_driven.signals import message_started, message_finished

from router.direct_message import DirectMessage
from router.flow_start import FlowStart
from nexus.intelligences.llms.client import LLMClient


app = FastAPI()


class Indexer:
    pass


def call_llm(
        indexer: Indexer,
        llm_model: LLMClient,
        message: Message,
        content_base_uuid: str,
        agent: AgentDTO,
        instructions: List[InstructionDTO]
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
    )

    gpt_message = response.get("answers")[0].get("text")

    return gpt_message


def get_chunks(indexer, text: str, content_base_uuid: str) -> List[str]:
    client = indexer
    response = client.search_data(content_base_uuid=content_base_uuid, text=text)
    if response.get("status") == 200:
        texts_chunks: List[str] = response.get("data")
        return texts_chunks


from router.clients.flows.http.broadcast import BroadcastHTTPClient
from router.clients.flows.http.flow_start import FlowStartHTTPClient


def route(
        classification: str,
        message: Message,
        content_base_repository: Repository,
        flows_repository: Repository,
        flows: List[FlowDTO],  # TODO: talvez não seja necessário, remover
        indexer: Indexer,
        llm_client: LLMClient,
        direct_message: DirectMessage,
        flow_start: FlowStart

    ):

    if classification == Classifier.CLASSIFICATION_OTHER:
        print(f"[- Fallback -]")

        fallback_flow: FlowDTO = flows_repository.project_flow_fallback(message.project_uuid, True)

        content_base: ContentBaseDTO = content_base_repository.get_content_base(message.project_uuid)
        agent: AgentDTO = content_base_repository.get_agent(content_base.uuid)
        instructions: List[InstructionDTO] = content_base_repository.list_instructions(content_base.uuid)

        llm_response: str = call_llm(
            indexer=indexer,
            llm_model=llm_client,
            message=message,
            content_base_uuid=content_base.uuid,
            agent=agent,
            instructions=instructions
        )

        if fallback_flow:
            dispatch(
                message=message,
                flow=fallback_flow.uuid,
                flow_start=flow_start,
                llm_response=llm_response,
                user_email="CRM@WENI.AI" # TODO: Descobrir quem é esse email/mandar o crm sempre?
            )
            return

        dispatch(
            llm_response=llm_response,
            message=message,
            direct_message=direct_message,
            user_email="CRM@WENI.AI" # TODO: Descobrir quem é esse email/mandar o crm sempre?
        )
        return

    flow: FlowDTO = flows_repository.get_project_flow_by_name(message.project_uuid, classification)

    dispatch(
        message=message,
        flow_start=flow_start,
        flow=flow.uuid,
        user_email="CRM@WENI.AI" # TODO: Descobrir quem é esse email/mandar o crm sempre?
    )


def dispatch(
        message: Message,
        user_email: str,
        flow: str = None,
        llm_response: str = None,
        direct_message: DirectMessage = None,
        flow_start: FlowStart = None
    ):
    urns = [message.contact_urn]

    if direct_message:

        print(f"[+ sending direct message to {message.contact_urn} +]")
    
        return direct_message.send_direct_message(
            llm_response,
            urns,
            message.project_uuid,
            user_email
        )
    
    print(f"[+ starting flow {flow} +]")

    return flow_start.start_flow(
        flow=flow,
        user=user_email,
        urns=urns,
    )


@app.post('/messages')
def messages(message: Message):
    message_started.send(sender=DBCon)
    try:

        print("[+ Mensagem recebida +]")

        flows_repository = FlowsORMRepository()
        content_base_repository = ContentBaseORMRepository()

        flows: List[FlowDTO] = flows_repository.project_flows(message.project_uuid, False)

        classification: str = classify(ZeroshotClassifier(), message.text, flows)

        print(f"[+ Mensagem classificada: {classification} +]")

        llm_client = LLMClient.get_by_type("chatgpt")  # TODO: get llm model from user

        broadcast = BroadcastHTTPClient(os.environ.get('FLOWS_REST_ENDPOINT'), os.environ.get('FLOWS_INTERNAL_TOKEN'))
        flow_start = FlowStartHTTPClient(os.environ.get('FLOWS_REST_ENDPOINT'), os.environ.get('FLOWS_INTERNAL_TOKEN'))

        route(
            classification=classification,
            message=message,
            content_base_repository=content_base_repository,
            flows_repository=flows_repository,
            flows=flows,
            indexer=SentenXFileDataBase(),
            llm_client=llm_client(),
            direct_message=broadcast,
            flow_start=flow_start
        )

    finally:
        message_finished.send(sender=DBCon)
    return {}


