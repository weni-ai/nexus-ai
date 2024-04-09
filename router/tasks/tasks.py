

import os
from typing import List, Dict

from fastapi import FastAPI

from router.repositories.orm import FlowsORMRepository, ContentBaseORMRepository
from router.classifiers.zeroshot import ZeroshotClassifier
from router.classifiers import classify
from router.entities import (
    FlowDTO,
    Message,
    LLMSetupDTO,
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

    llm_model = get_llm_by_project_uuid(project_uuid)

    llm_config = LLMSetupDTO(
        model=llm_model.model.lower(),
        model_version=llm_model.setup.get("version"),
        temperature=llm_model.setup.get("temperature"),
        top_k=llm_model.setup.get("top_k"),
        top_p=llm_model.setup.get("top_p"),
        token=llm_model.setup.get("token"),
        max_length=llm_model.setup.get("max_length"),
        max_tokens=llm_model.setup.get("max_tokens"),
    )

    llm_client = LLMClient.get_by_type(llm_config.model)

    llm_client = list(llm_client)[0]()

    if llm_config.model.lower() != "wenigpt":
        llm_client.token = llm_config.token

    print(f"[+ Modelo escolhido: {llm_config.model} +]")

    broadcast = BroadcastHTTPClient(os.environ.get('FLOWS_REST_ENDPOINT'), os.environ.get('FLOWS_INTERNAL_TOKEN'))
    flow_start = FlowStartHTTPClient(os.environ.get('FLOWS_REST_ENDPOINT'), os.environ.get('FLOWS_INTERNAL_TOKEN'))
    flows_user_email = os.environ.get("FLOW_USER_EMAIL")

    route(
        classification=classification,
        message=message,
        content_base_repository=content_base_repository,
        flows_repository=flows_repository,
        indexer=SentenXFileDataBase(),
        llm_client=llm_client,
        direct_message=broadcast,
        flow_start=flow_start,
        llm_config=llm_config,
        flows_user_email=flows_user_email
    )