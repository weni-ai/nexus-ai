

import os
from typing import Dict

from django.conf import settings

from nexus.celery import app as celery_app
from nexus.intelligences.llms.client import LLMClient
from nexus.usecases.intelligences.get_by_uuid import get_llm_by_project_uuid
from nexus.usecases.logs.create import CreateLogUsecase

from router.route import route
from router.classifiers.zeroshot import ZeroshotClassifier

from router.classifiers.pre_classification import PreClassification
from router.classifiers.classification import Classification
from router.clients.flows.http.flow_start import FlowStartHTTPClient
from router.clients.flows.http.send_message import SendMessageHTTPClient
from router.entities import (
    Message, AgentDTO, ContentBaseDTO, LLMSetupDTO
)
from router.repositories.orm import (
    ContentBaseORMRepository,
    FlowsORMRepository,
    MessageLogsRepository
)
from nexus.usecases.projects.projects_use_case import ProjectsUseCase


@celery_app.task
def start_route(
    message: Dict
) -> bool:  # pragma: no cover

    print(f"[+ Message received: {message} +]")

    content_base_repository = ContentBaseORMRepository()
    message_logs_repository = MessageLogsRepository()

    message = Message(**message)
    mailroom_msg_event = message.msg_event
    mailroom_msg_event['attachments'] = mailroom_msg_event.get(
        'attachments') or []
    mailroom_msg_event['metadata'] = mailroom_msg_event.get('metadata') or {}

    log_usecase = CreateLogUsecase()
    try:
        project_uuid: str = message.project_uuid
        indexer = ProjectsUseCase().get_indexer_database_by_uuid(project_uuid)
        flows_repository = FlowsORMRepository(project_uuid=project_uuid)

        broadcast = SendMessageHTTPClient(os.environ.get(
            'FLOWS_REST_ENDPOINT'), os.environ.get('FLOWS_SEND_MESSAGE_INTERNAL_TOKEN'))
        flow_start = FlowStartHTTPClient(os.environ.get(
            'FLOWS_REST_ENDPOINT'), os.environ.get('FLOWS_INTERNAL_TOKEN'))
        flows_user_email = os.environ.get("FLOW_USER_EMAIL")

        content_base: ContentBaseDTO = content_base_repository.get_content_base_by_project(
            message.project_uuid)
        agent: AgentDTO = content_base_repository.get_agent(content_base.uuid)
        agent = agent.set_default_if_null()

        pre_classification = PreClassification(
            flows_repository=flows_repository,
            message=message,
            msg_event=mailroom_msg_event,
            flow_start=flow_start,
            user_email=flows_user_email
        )

        if pre_classification.pre_classification_route():
            return True

        classification_handler = Classification(
            flows_repository=flows_repository,
            message=message,
            msg_event=mailroom_msg_event,
            flow_start=flow_start,
            user_email=flows_user_email
        )

        if classification_handler.non_custom_actions_route():
            return True

        log_usecase.create_message_log(
            text=message.text,
            contact_urn=message.contact_urn,
            source="router",
        )

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
            language=llm_model.setup.get(
                "language", settings.WENIGPT_DEFAULT_LANGUAGE),
        )

        classifier = ZeroshotClassifier(chatbot_goal=agent.goal)
        classification = classification_handler.custom_actions(
            classifier=classifier,
            language=llm_config.language
        )

        llm_client = LLMClient.get_by_type(llm_config.model)
        llm_client: LLMClient = list(llm_client)[0](
            model_version=llm_config.model_version)

        if llm_config.model.lower() != "wenigpt":
            llm_client.api_key = llm_config.token

        route(
            classification=classification,
            message=message,
            content_base_repository=content_base_repository,
            flows_repository=flows_repository,
            message_logs_repository=message_logs_repository,
            indexer=indexer(),
            llm_client=llm_client,
            direct_message=broadcast,
            flow_start=flow_start,
            llm_config=llm_config,
            flows_user_email=flows_user_email,
            log_usecase=log_usecase
        )

        log_usecase.update_status("S")
    except Exception as e:
        print(f"[- START ROUTE - Error: {e} -]")
        if message.text:
            log_usecase.update_status("F", exception_text=e)
