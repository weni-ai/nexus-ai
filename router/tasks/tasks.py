import os
import uuid
from typing import Dict

from django.conf import settings
from redis import Redis

from nexus.celery import app as celery_app
from nexus.intelligences.llms.client import LLMClient
from nexus.usecases.intelligences.get_by_uuid import get_llm_by_project_uuid
from nexus.usecases.logs.create import CreateLogUsecase

from router.route import route
from router.classifiers.chatgpt_function import ChatGPTFunctionClassifier

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
from nexus.usecases.intelligences.retrieve import get_file_info
from nexus.usecases.agents.agents import AgentUsecase
from nexus.usecases.intelligences.get_by_uuid import (
    get_default_content_base_by_project,
)

from router.clients.preview.simulator.broadcast import SimulateBroadcast
from router.clients.preview.simulator.flow_start import SimulateFlowStart
from router.dispatcher import dispatch

from nexus.projects.models import Project


def get_action_clients(preview: bool = False):
    if preview:
        flow_start = SimulateFlowStart(
            os.environ.get(
                'FLOWS_REST_ENDPOINT'
            ),
            os.environ.get(
                'FLOWS_INTERNAL_TOKEN'
            )
        )
        broadcast = SimulateBroadcast(
            os.environ.get(
                'FLOWS_REST_ENDPOINT'
            ),
            os.environ.get(
                'FLOWS_INTERNAL_TOKEN'
            ),
            get_file_info
        )
        return broadcast, flow_start

    broadcast = SendMessageHTTPClient(
        os.environ.get(
            'FLOWS_REST_ENDPOINT'
        ),
        os.environ.get(
            'FLOWS_SEND_MESSAGE_INTERNAL_TOKEN'
        )
    )
    flow_start = FlowStartHTTPClient(
        os.environ.get(
            'FLOWS_REST_ENDPOINT'
        ),
        os.environ.get(
            'FLOWS_INTERNAL_TOKEN'
        )
    )
    return broadcast, flow_start


@celery_app.task(bind=True)
def start_route(self, message: Dict, preview: bool = False) -> bool:  # pragma: no cover
    # TODO: remove get_action_clients from this function
    def get_action_clients(preview: bool = False):
        if preview:
            flow_start = SimulateFlowStart(
                os.environ.get(
                    'FLOWS_REST_ENDPOINT'
                ),
                os.environ.get(
                    'FLOWS_INTERNAL_TOKEN'
                )
            )
            broadcast = SimulateBroadcast(
                os.environ.get(
                    'FLOWS_REST_ENDPOINT'
                ),
                os.environ.get(
                    'FLOWS_INTERNAL_TOKEN'
                ),
                get_file_info
            )
            return broadcast, flow_start

        broadcast = SendMessageHTTPClient(
            os.environ.get(
                'FLOWS_REST_ENDPOINT'
            ),
            os.environ.get(
                'FLOWS_SEND_MESSAGE_INTERNAL_TOKEN'
            )
        )
        flow_start = FlowStartHTTPClient(
            os.environ.get(
                'FLOWS_REST_ENDPOINT'
            ),
            os.environ.get(
                'FLOWS_INTERNAL_TOKEN'
            )
        )
        return broadcast, flow_start

    source = "preview" if preview else "router"
    print(f"[+ Message from: {source} +]")

    # Initialize Redis client using the REDIS_URL from settings
    redis_client = Redis.from_url(settings.REDIS_URL)

    print(f"[+ Message received: {message} +]")

    content_base_repository = ContentBaseORMRepository()
    message_logs_repository = MessageLogsRepository()

    message = Message(**message)
    mailroom_msg_event = message.msg_event
    mailroom_msg_event['attachments'] = mailroom_msg_event.get(
        'attachments'
    ) or []
    mailroom_msg_event['metadata'] = mailroom_msg_event.get('metadata') or {}

    log_usecase = CreateLogUsecase()

    try:
        project_uuid: str = message.project_uuid
        indexer = ProjectsUseCase().get_indexer_database_by_uuid(project_uuid)
        flows_repository = FlowsORMRepository(project_uuid=project_uuid)

        broadcast, flow_start = get_action_clients(preview)

        flows_user_email = os.environ.get("FLOW_USER_EMAIL")

        content_base: ContentBaseDTO = content_base_repository.get_content_base_by_project(
            message.project_uuid
        )
        agent: AgentDTO = content_base_repository.get_agent(content_base.uuid)
        agent = agent.set_default_if_null()

        pre_classification = PreClassification(
            flows_repository=flows_repository,
            message=message,
            msg_event=mailroom_msg_event,
            flow_start=flow_start,
            user_email=flows_user_email
        )

        pre_classification = pre_classification.pre_classification(source=source)
        if pre_classification:
            return pre_classification if source == "preview" else True

        classification_handler = Classification(
            flows_repository=flows_repository,
            message=message,
            msg_event=mailroom_msg_event,
            flow_start=flow_start,
            user_email=flows_user_email
        )

        non_custom_actions = classification_handler.non_custom_actions(source=source)
        if non_custom_actions:
            return non_custom_actions if source == "preview" else True

        message_log = log_usecase.create_message_log(
            text=message.text,
            contact_urn=message.contact_urn,
            source=source,
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
                "language", settings.WENIGPT_DEFAULT_LANGUAGE
            ),
        )

        classifier = ChatGPTFunctionClassifier(agent_goal=agent.goal)

        classification = classification_handler.custom_actions(
            classifier=classifier,
            language=llm_config.language
        )

        llm_client = LLMClient.get_by_type(llm_config.model)
        llm_client: LLMClient = list(llm_client)[0](
            model_version=llm_config.model_version,
            api_key=llm_config.token
        )

        # Check if there's a pending response for this user
        pending_response_key = f"response:{message.contact_urn}"
        pending_task_key = f"task:{message.contact_urn}"
        pending_response = redis_client.get(pending_response_key)
        pending_task_id = redis_client.get(pending_task_key)

        if pending_response:
            # Revoke the previous task
            if pending_task_id:
                celery_app.control.revoke(pending_task_id.decode('utf-8'), terminate=True)

            # Concatenate the previous message with the new one
            previous_message = pending_response.decode('utf-8')
            concatenated_message = f"{previous_message}\n{message.text}"
            message.text = concatenated_message
            redis_client.delete(pending_response_key)  # Remove the pending response
        else:
            # Store the current message in Redis
            redis_client.set(pending_response_key, message.text)

        # Store the current task ID in Redis
        redis_client.set(pending_task_key, self.request.id)

        # Generate response for the concatenated message
        response: dict = route(
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
            log_usecase=log_usecase,
            message_log=message_log
        )

        # If response generation completes, remove from Redis
        redis_client.delete(pending_response_key)
        redis_client.delete(pending_task_key)

        log_usecase.update_status("S")

        return response

    except Exception as e:
        print(f"[- START ROUTE - Error: {e} -]")
        if message.text:
            log_usecase.update_status("F", exception_text=e)


@celery_app.task(bind=True)
def start_multi_agents(self, message: Dict, preview: bool = False) -> bool:  # pragma: no cover
    # TODO: Logs

    project = Project.objects.get(uuid=message.get("project_uuid"))
    supervisor = project.team
    self.contentbase = get_default_content_base_by_project(self.project.uuid)
    usecase = AgentUsecase()
    usecase.prepare_agent(supervisor.external_id)
    session_id = f"project-{project.uuid}-session-{uuid.uuid4()}"
    full_response = usecase.invoke_supervisor(
        session_id=session_id,
        supervisor_id=supervisor.external_id,
        supervisor_alias_id=supervisor.metadata.get("supervisor_alias_id"),
        prompt=message.get("text"),
        content_base_uuid=str(self.contentbase.uuid),
    )

    broadcast, _ = get_action_clients(preview)
    flows_user_email = os.environ.get("FLOW_USER_EMAIL")

    full_chunks = []

    return dispatch(
        llm_response=full_response,
        message=Message(**message),
        direct_message=broadcast,
        user_email=flows_user_email,
        full_chunks=full_chunks,
    )
