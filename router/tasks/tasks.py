

import os
from typing import List, Dict

from django.conf import settings

from nexus.celery import app as celery_app
from nexus.intelligences.llms.client import LLMClient
from nexus.usecases.intelligences.get_by_uuid import get_llm_by_project_uuid
from nexus.usecases.logs.create import CreateLogUsecase
from nexus.usecases.actions.retrieve import get_flow_by_action_type
from nexus.usecases.projects.projects_use_case import ProjectsUseCase

from router.route import route
from router.classifiers.zeroshot import ZeroshotClassifier
from router.classifiers.chatgpt_function import OpenAIClient, ChatGPTFunctionClassifier
from router.classifiers import classify
from router.flow_start.interfaces import FlowStart
from router.clients.flows.http.flow_start import FlowStartHTTPClient
from router.clients.flows.http.send_message import SendMessageHTTPClient
from router.entities import (
    FlowDTO, Message, AgentDTO, ContentBaseDTO, LLMSetupDTO
)
from router.repositories.orm import (
    ContentBaseORMRepository,
    FlowsORMRepository,
    MessageLogsRepository,
)


def whatsapp_cart_flow(
    content_base: ContentBaseDTO,
    message: Message,
    msg_event: dict,
    flow_start: FlowStart
) -> bool:
    flow = get_flow_by_action_type(
        content_base_uuid=content_base.uuid,
        action_type="whatsapp_cart"
    )
    flow_dto = FlowDTO(
        content_base_uuid=content_base.uuid,
        uuid=flow.uuid,
        name=flow.name,
        prompt=flow.prompt,
        fallback=flow.fallback,
    )

    if flow:
        flow_start.start_flow(
            flow=flow_dto,
            user=os.environ.get("FLOW_USER_EMAIL"),
            urn=[message.contact_urn],
            user_message="",
            msg_event=msg_event,
        )
        return True
    return False


@celery_app.task
def start_route(
    message: Dict
) -> bool:  # pragma: no cover

    print(f"[+ Message received: {message} +]")

    flows_repository = FlowsORMRepository()
    content_base_repository = ContentBaseORMRepository()
    message_logs_repository = MessageLogsRepository()

    message = Message(**message)
    mailroom_msg_event = message.msg_event

    try:
        project_uuid: str = message.project_uuid

        broadcast = SendMessageHTTPClient(os.environ.get('FLOWS_REST_ENDPOINT'), os.environ.get('FLOWS_SEND_MESSAGE_INTERNAL_TOKEN'))
        flow_start = FlowStartHTTPClient(os.environ.get('FLOWS_REST_ENDPOINT'), os.environ.get('FLOWS_INTERNAL_TOKEN'))
        flows_user_email = os.environ.get("FLOW_USER_EMAIL")
        indexer = ProjectsUseCase().get_indexer_database(project_uuid)

        flows: List[FlowDTO] = flows_repository.project_flows(project_uuid, False)
        content_base: ContentBaseDTO = content_base_repository.get_content_base_by_project(message.project_uuid)
        agent: AgentDTO = content_base_repository.get_agent(content_base.uuid)
        agent = agent.set_default_if_null()

        if 'order' in message.metadata:
            print("[+ WhatsApp Cart Flow +]")
            return whatsapp_cart_flow(
                content_base=content_base,
                message=message,
                msg_event=mailroom_msg_event,
                flow_start=flow_start
            )

        log_usecase = CreateLogUsecase()
        log_usecase.create_message_log(message.text, message.contact_urn)

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
            client = OpenAIClient(api_key=llm_config.token)
            classifier = ChatGPTFunctionClassifier(
                client=client,
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
        log_usecase.update_status("F", exception_text=e)
