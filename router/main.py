
import os
from typing import List, Dict

from fastapi import FastAPI

from router.repositories.orm import FlowsORMRepository, ContentBaseRepository
from router.repositories import Repository
from router.classifiers.zeroshot import ZeroshotClassifier
from router.classifiers import Classifier
from router.classifiers import classify
from router.entities import (
    FlowDTO, Message, DBCon, AgentDTO, InstructionDTO
)
from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase

from nexus.event_driven.signals import message_started, message_finished
from nexus.intelligences.llms import ChatGPTClient

from router.direct_message import DirectMessage
from router.flow_start import FlowStart

app = FastAPI()


def route(direct_message: DirectMessage, flow_start: FlowStart):
    pass


def start_flow(flow: FlowDTO, message: Message, params: Dict):
    print(f"[+ Iniciando fluxo para contato {message.contact_urn} +]")
    print(f"[+ Message: {params} +]")
    client = FlowStartHTTPClient(os.environ.get('FLOWS_REST_ENDPOINT'), os.environ.get('FLOWS_INTERNAL_TOKEN'))
    client.start_flow(flow.uuid, "crm@weni.ai", [message.contact_urn])


def call_llm(
        indexer,
        llm_model,
        message: Message,
        fallback_flow: FlowDTO,
        agent: AgentDTO,
        instructions: List[InstructionDTO]
    ) -> str:

    chunks: List[str] = get_chunks(
        indexer,
        text=message.text,
        content_base_uuid=fallback_flow.content_base_uuid
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


def dispatch(classification: str, message: Message, content_base_repository: Repository, flows_repository: Repository):
    if classification == Classifier.CLASSIFICATION_OTHER:

        print(f"[- Fallback -]")

        fallback_flow: FlowDTO = flows_repository.project_flow_fallback(message.project_uuid, True)
        agent: AgentDTO = content_base_repository.get_agent(fallback_flow.content_base_uuid)
        instructions: List[InstructionDTO] = content_base_repository.list_instructions(fallback_flow.content_base_uuid)

        # call_llm(SentenXFileDataBase(), message, fallback_flow)
        llm_response: str = call_llm(Indexer(), ChatGPTClient(), message, fallback_flow, agent, instructions)
        broadcast = BroadcastHTTPClient(os.environ.get('FLOWS_REST_ENDPOINT'), os.environ.get('FLOWS_INTERNAL_TOKEN'))
        broadcast.send_direct_message(llm_response, [message.contact_urn], message.project_uuid, "crm@weni.ai")

        return {}

    for flow in flows:
        if classification == flow.name:
            print("[+ Fluxo +]")
            start_flow(flow, message, params={"input": message.text}))




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
        dispatch(classification)
        
    finally:
        message_finished.send(sender=DBCon)
    return {}


class LLM:
    def request_gpt(self):
        return {"answers":[{"text": "Resposta do LLM"}],"id":"0"}

class Indexer:
    def search_data(self, content_base_uuid: str, text: str):
        return {
            "status": 200,
            "data": ["Lorem Ipsum"]
        }