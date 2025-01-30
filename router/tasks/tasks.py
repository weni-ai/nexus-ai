import os
import uuid
import json
import time
from typing import Dict
from tenacity import retry, stop_after_attempt, wait_exponential
from openai import OpenAI

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
    message_factory, AgentDTO, ContentBaseDTO, LLMSetupDTO
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
from nexus.projects.websockets.consumers import send_preview_message_to_websocket

client = OpenAI()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def get_trace_summary(language, trace):
    try:
        # Add a small delay between API calls to respect rate limits
        time.sleep(3)

        prompt = f"""
          Generate a concise, one-line summary of the trace of the action, in {language}.
          This summary must describe the orchestrator's action, referring to all actions as "skills."

          Guidelines for your response:
          - Use the following language for the summary: {language}.
          - The text to be summarized is the trace of the action.
          - Use a systematic style (e.g., "Cancel Order skill activated", "Forwarding request to Reporting skill").
          - The summary must not exceed 10 words.
          - Use varied gerunds (e.g., "Checking", "Cancelling", "Forwarding").
          - Do not include technical details about models, architectures, language codes, or anything unrelated to summarizing the action.

          Here is the trace of the action:
          {json.dumps(trace, indent=2)}
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=100,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error getting trace summary: {str(e)}")
        return "Processing your request now"

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

    message = message_factory(
        project_uuid=message.get("project_uuid"),
        text=message.get("text"),
        contact_urn=message.get("contact_urn"),
        metadata=message.get("metadata"),
        attachments=message.get("attachments"),
        msg_event=message.get("msg_event"),
        contact_fields=message.get("contact_fields", {}),
    )

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
def start_multi_agents(self, message: Dict, preview: bool = False, language: str = "en", user_email: str = '') -> bool:  # pragma: no cover
    # TODO: Logs
    message = message_factory(
        project_uuid=message.get("project_uuid"),
        text=message.get("text"),
        contact_urn=message.get("contact_urn"),
        metadata=message.get("metadata"),
        attachments=message.get("attachments"),
        msg_event=message.get("msg_event"),
        contact_fields=message.get("contact_fields", {}),
    )

    project = Project.objects.get(uuid=message.project_uuid)

    supervisor = project.team
    supervisor_version = supervisor.current_version

    contentbase = get_default_content_base_by_project(message.project_uuid)

    usecase = AgentUsecase()
    session_id = f"project-{project.uuid}-session-{uuid.uuid4()}"

    if user_email:
        # Send initial status through WebSocket
        send_preview_message_to_websocket(
            project_uuid=str(project.uuid),
            user_email=user_email,
            message_data={
                "type": "status",
                "content": "Starting multi-agent processing",
                "session_id": session_id
            }
        )

    try:
        # Stream supervisor response
        full_response = ""
        for event in usecase.invoke_supervisor_stream(
            session_id=session_id,
            supervisor_id=supervisor.external_id,
            supervisor_alias_id=supervisor_version.alias_id,
            prompt=message.text,
            content_base_uuid=str(contentbase.uuid),
        ):
            if event['type'] == 'chunk':
                chunk = event['content']
                full_response += chunk
                if user_email:
                    # Send chunk through WebSocket
                    send_preview_message_to_websocket(
                        project_uuid=str(project.uuid),
                        user_email=user_email,
                        message_data={
                            "type": "chunk",
                            "content": chunk,
                            "session_id": session_id
                        }
                    )
            elif event['type'] == 'trace':
                # Get summary from Claude with specified language
                event['content']['summary'] = get_trace_summary(language, event['content'])
                if user_email:
                    # Send trace data through WebSocket
                    send_preview_message_to_websocket(
                        project_uuid=str(project.uuid),
                        user_email=user_email,
                        message_data={
                            "type": "trace_update",
                            "trace": event['content'],
                            "session_id": session_id
                        }
                    )

        broadcast, _ = get_action_clients(preview)
        flows_user_email = os.environ.get("FLOW_USER_EMAIL")

        full_chunks = []

        if user_email:
            # Send completion status
            send_preview_message_to_websocket(
                user_email=user_email,
                project_uuid=str(project.uuid),
                message_data={
                    "type": "status",
                    "content": "Processing complete",
                    "session_id": session_id
                }
            )

        return dispatch(
            llm_response=full_response,
            message=message,
            direct_message=broadcast,
            user_email=flows_user_email,
            full_chunks=full_chunks,
        )

    except Exception as e:
        if user_email:
          # Send error status through WebSocket
          send_preview_message_to_websocket(
              user_email=user_email,
              project_uuid=str(project.uuid),
              message_data={
                  "type": "error",
                  "content": str(e),
                  "session_id": session_id
              }
          )
        raise
