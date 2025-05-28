import os
from typing import Dict

import botocore
from django.conf import settings
from redis import Redis

from inline_agents.backends import BackendsRegistry
from nexus.celery import app as celery_app
from nexus.inline_agents.team.repository import ORMTeamRepository
from nexus.projects.models import Project
from nexus.projects.websockets.consumers import (
    send_preview_message_to_websocket,
)
from nexus.usecases.inline_agents.typing import TypingUsecase
from router.dispatcher import dispatch
from router.entities import message_factory

from .actions_client import get_action_clients


def handle_product_items(text: str, product_items: list) -> str:
    if text:
        text = f"{text} product items: {str(product_items)}"
    else:
        text = f"product items: {str(product_items)}"
    return text


@celery_app.task(
    bind=True, 
    soft_time_limit=300, 
    time_limit=360,
    acks_late=True,
    autoretry_for=(botocore.exceptions.EventStreamError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5
)
def start_inline_agents(
    self,
    message: Dict,
    preview: bool = False,
    language: str = "en",
    user_email: str = ''
) -> bool:  # pragma: no cover

    redis_client = Redis.from_url(settings.REDIS_URL)

    # Handle text, attachments and product items properly
    text = message.get("text", "")
    attachments = message.get("attachments", [])
    message_event = message.get("msg_event", {})
    product_items = message.get("metadata", {}).get("order", {}).get("product_items", [])

    typing_usecase = TypingUsecase()
    if not preview:
        typing_usecase.send_typing_message(
            contact_urn=message.get("contact_urn"),
            msg_external_id=message_event.get("msg_external_id", ""),
            project_uuid=message.get("project_uuid")
        )

    if attachments:
        if text:
            text = f"{text} {attachments}"
        else:
            text = str(attachments)

    if len(product_items) > 0:
        text = handle_product_items(text, product_items)

    # Update the message with the processed text
    message['text'] = text

    # TODO: Logs
    message = message_factory(
        project_uuid=message.get("project_uuid"),
        text=text,
        contact_urn=message.get("contact_urn"),
        metadata=message.get("metadata"),
        attachments=attachments,
        msg_event=message.get("msg_event"),
        contact_fields=message.get("contact_fields", {}),
    )

    print(f"[DEBUG] Message: {message}")

    redis_client = Redis.from_url(settings.REDIS_URL)

    project = Project.objects.get(uuid=message.project_uuid)

    # Check for pending responses
    pending_response_key = f"response:{message.project_uuid}:{message.contact_urn}"
    pending_task_key = f"task:{message.project_uuid}:{message.contact_urn}"

    pending_response = redis_client.get(pending_response_key)
    pending_task_id = redis_client.get(pending_task_key)

    if pending_response:
        if pending_task_id:
            celery_app.control.revoke(pending_task_id.decode('utf-8'), terminate=True)

        previous_message = pending_response.decode('utf-8')
        concatenated_message = f"{previous_message}\n{message.text}"
        message.text = concatenated_message
        redis_client.delete(pending_response_key)
    else:
        redis_client.set(pending_response_key, message.text)

    redis_client.set(pending_task_key, self.request.id)

    print(f"[DEBUG] Email sent: {user_email}")
    if user_email:
        send_preview_message_to_websocket(
            project_uuid=message.project_uuid,
            user_email=user_email,
            message_data={
                "type": "status",
                "content": "Starting multi-agent processing",
                # "session_id": session_id # TODO: add session_id
            }
        )

    project_use_components = project.use_components

    try:
        broadcast, _ = get_action_clients(preview, multi_agents=True, project_use_components=project_use_components)

        flows_user_email = os.environ.get("FLOW_USER_EMAIL")

        agents_backend = project.agents_backend
        backend = BackendsRegistry.get_backend(agents_backend)

        rep = ORMTeamRepository()
        team = rep.get_team(message.project_uuid)

        response = backend.invoke_agents(
            team=team,
            input_text=message.text,
            contact_urn=message.contact_urn,
            project_uuid=message.project_uuid,
            preview=preview,
            rationale_switch=project.rationale_switch,
            sanitized_urn=message.sanitized_urn,
            language=language,
            user_email=user_email,
            use_components=project.use_components,
            contact_fields=message.contact_fields_as_json,
            msg_external_id=message_event.get("msg_external_id", "")
        )

        redis_client.delete(pending_response_key)
        redis_client.delete(pending_task_key)
        return dispatch(
            llm_response=response,
            message=message,
            direct_message=broadcast,
            user_email=flows_user_email,
            full_chunks=[],
        )

    except Exception as e:
        redis_client.delete(pending_response_key)
        redis_client.delete(pending_task_key)

        print(f"[DEBUG] Error in start_inline_agents: {str(e)}")
        print(f"[DEBUG] Error type: {type(e)}")
        print(f"[DEBUG] Full exception details: {e.__dict__}")

        if user_email:
            send_preview_message_to_websocket(
                user_email=user_email,
                project_uuid=str(project.uuid),
                message_data={
                    "type": "error",
                    "content": str(e),
                    # "session_id": session_id TODO: add session_id
                }
            )
        raise
