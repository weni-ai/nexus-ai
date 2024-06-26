

import os
from typing import List, Dict

from django.conf import settings

from nexus.task_managers.file_database.sentenx_file_database import SentenXFileDataBase
from nexus.celery import app as celery_app
from nexus.intelligences.llms.client import LLMClient
from nexus.usecases.intelligences.get_by_uuid import get_llm_by_project_uuid
from nexus.usecases.logs.create import CreateLogUsecase

from router.route import route
from router.classifiers.zeroshot import ZeroshotClassifier
from router.classifiers.chatgpt_function import ChatGPT_Function_Classifier
from router.classifiers import classify
from router.clients.flows.http.flow_start import FlowStartHTTPClient
from router.clients.flows.http.send_message import SendMessageHTTPClient
from router.entities import (
    FlowDTO, Message, AgentDTO, ContentBaseDTO, LLMSetupDTO
)
from router.repositories.orm import (
    ContentBaseORMRepository,
    FlowsORMRepository,
    MessageLogsRepository
)


@celery_app.task
def start_route(message: Dict) -> bool:

    print(f"[+ Message received: {message} +]")

    flows_repository = FlowsORMRepository()
    content_base_repository = ContentBaseORMRepository()
    message_logs_repository = MessageLogsRepository()

    message = Message(**message)

    log_usecase = CreateLogUsecase()
    log_usecase.create_message_log(message.text, message.contact_urn)

    try:
        project_uuid: str = message.project_uuid

        flows: List[FlowDTO] = flows_repository.project_flows(project_uuid, False)
        content_base: ContentBaseDTO = content_base_repository.get_content_base_by_project(message.project_uuid)
        agent: AgentDTO = content_base_repository.get_agent(content_base.uuid)
        agent = agent.set_default_if_null()

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
            language=llm_model.setup.get("language", settings.WENIGPT_DEFAULT_LANGUAGE),
        )

        if llm_config.model.lower() == "chatgpt":
            classifier = ChatGPT_Function_Classifier(
                api_key=llm_config.token,
                chatgpt_model=llm_config.model_version,
            )
        else:
            classifier = ZeroshotClassifier(
                chatbot_goal=agent.goal
            )

        classification = classify(
            classifier=classifier,
            message=message.text,
            flows=flows,
            language=llm_config.language
        )

        print(f"[+ Classification: {classification} +]")

        llm_client = LLMClient.get_by_type(llm_config.model)
        llm_client: LLMClient = list(llm_client)[0](model_version=llm_config.model_version)

        if llm_config.model.lower() != "wenigpt":
            llm_client.api_key = llm_config.token

        broadcast = SendMessageHTTPClient(os.environ.get('FLOWS_REST_ENDPOINT'), os.environ.get('FLOWS_SEND_MESSAGE_INTERNAL_TOKEN'))
        flow_start = FlowStartHTTPClient(os.environ.get('FLOWS_REST_ENDPOINT'), os.environ.get('FLOWS_INTERNAL_TOKEN'))
        flows_user_email = os.environ.get("FLOW_USER_EMAIL")

        route(
            classification=classification,
            message=message,
            content_base_repository=content_base_repository,
            flows_repository=flows_repository,
            message_logs_repository=message_logs_repository,
            indexer=SentenXFileDataBase(),
            llm_client=llm_client,
            direct_message=broadcast,
            flow_start=flow_start,
            llm_config=llm_config,
            flows_user_email=flows_user_email,
            log_usecase=log_usecase
        )

        log_usecase.update_status("S")
    except Exception as e:
        log_usecase.update_status("F", exception_text=e)
