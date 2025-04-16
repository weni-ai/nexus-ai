import os
from typing import Dict

from django.conf import settings
from redis import Redis

from inline_agents.backends import BackendsRegistry
from nexus.celery import app as celery_app
from nexus.inline_agents.team.repository import ORMTeamRepository
from nexus.projects.models import Project
from nexus.projects.websockets.consumers import (
    send_preview_message_to_websocket,
)
from router.dispatcher import dispatch
from router.entities import (
    message_factory,
)

from .actions_client import get_action_clients


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360)
def start_inline_agents(
    self,
    message: Dict,
    preview: bool = False,
    language: str = "en",
    user_email: str = ''
) -> bool:  # pragma: no cover

    # Initialize Redis client
    redis_client = Redis.from_url(settings.REDIS_URL)

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

    print(f"[DEBUG] Message: {message}")

    # Initialize Redis client
    redis_client = Redis.from_url(settings.REDIS_URL)

    # Check if there's a pending response for this user
    pending_response_key = f"multi_response:{message.contact_urn}"
    pending_task_key = f"multi_task:{message.contact_urn}"
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

    project = Project.objects.get(uuid=message.project_uuid)

    # Check for pending responses
    pending_response_key = f"response:{message.contact_urn}"
    pending_task_key = f"task:{message.contact_urn}"
    pending_response = redis_client.get(pending_response_key)
    pending_task_id = redis_client.get(pending_task_key)

    if pending_response:
        # Revoke the previous task if it exists
        if pending_task_id:
            celery_app.control.revoke(pending_task_id.decode('utf-8'), terminate=True)

        # Concatenate the previous message with the new one
        previous_message = pending_response.decode('utf-8')
        concatenated_message = f"{previous_message}\n{message.text}"
        message.text = concatenated_message
        redis_client.delete(pending_response_key)
    else:
        # Store the current message in Redis
        redis_client.set(pending_response_key, message.text)

    # Store the current task ID in Redis
    redis_client.set(pending_task_key, self.request.id)

    print(f"[DEBUG] Email sent: {user_email}")
    if user_email:
        # Send initial status through WebSocket
        send_preview_message_to_websocket(
            project_uuid=message.project_uuid,
            user_email=user_email,
            message_data={
                "type": "status",
                "content": "Starting multi-agent processing",
                # "session_id": session_id # TODO: add session_id
            }
        )

    project_use_components = message.project_uuid in settings.PROJECT_COMPONENTS

    try:
        # Stream supervisor response
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
            user_email=user_email
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
        # Clean up Redis entries in case of error
        redis_client.delete(pending_response_key)
        redis_client.delete(pending_task_key)

        print(f"[DEBUG] Error in start_inline_agents: {str(e)}")
        print(f"[DEBUG] Error type: {type(e)}")
        print(f"[DEBUG] Full exception details: {e.__dict__}")

        if user_email:
            # Send error status through WebSocket
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
