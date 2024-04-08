

import os
from typing import List, Dict

from fastapi import FastAPI

from router.repositories.orm import FlowsORMRepository, ContentBaseORMRepository
from router.classifiers.zeroshot import ZeroshotClassifier
from router.classifiers import classify
from router.entities import (
    FlowDTO,
    Message,
)

from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase

from nexus.celery import app as celery_app

from nexus.intelligences.llms.client import LLMClient

from router.clients.flows.http.broadcast import BroadcastHTTPClient
from router.clients.flows.http.flow_start import FlowStartHTTPClient

from router.route import route

from nexus.usecases.intelligences.get_by_uuid import get_llm_by_project_uuid


@celery_app.task
def start_route(message: Dict) -> bool:
    flows_repository = FlowsORMRepository()
    content_base_repository = ContentBaseORMRepository()

    message = Message(**message)
    project_uuid: str = message.project_uuid

    flows: List[FlowDTO] = flows_repository.project_flows(project_uuid, False)

    classification: str = classify(ZeroshotClassifier(), message.text, flows)

    print(f"[+ Mensagem classificada: {classification} +]")

    llm_config = get_llm_by_project_uuid(project_uuid)

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
        llm_client=list(llm_client)[0](),
        direct_message=broadcast,
        flow_start=flow_start,
        llm_config=llm_config,
    )