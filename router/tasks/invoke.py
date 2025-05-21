import os
from typing import Dict, Optional

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
from router.tasks.redis_task_manager import RedisTaskManager

from .actions_client import get_action_clients


def get_task_manager() -> RedisTaskManager:
    """Get the default task manager instance."""
    return RedisTaskManager()


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360)
def start_inline_agents(
    self,
    message: Dict,
    preview: bool = False,
    language: str = "en",
    user_email: str = '',
    task_manager: Optional[RedisTaskManager] = None
) -> bool:  # pragma: no cover

    # Initialize Redis task manager
    task_manager = task_manager or get_task_manager()

    # Handle text and attachments properly
    text = message.get("text", "")
    attachments = message.get("attachments", [])

    if attachments:
        # If there's text, add a space before attachments
        if text:
            text = f"{text} {attachments}"
        else:
            # If there's no text, just use attachments as text
            text = str(attachments)

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

    project = Project.objects.get(uuid=message.project_uuid)

    # Check for pending responses and handle them
    pending_task_id = task_manager.get_pending_task_id(message.contact_urn)
    if pending_task_id:
        # Revoke the previous task if it exists
        celery_app.control.revoke(pending_task_id, terminate=True)

    # Handle pending response and get final message text
    final_message_text = task_manager.handle_pending_response(message.contact_urn, message.text)
    message.text = final_message_text

    # Store the current task ID
    task_manager.store_pending_task_id(message.contact_urn, self.request.id)

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

    project_use_components = project.use_components

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
            user_email=user_email,
            use_components=project.use_components,
            contact_fields=message.contact_fields_as_json
        )

        # Clear pending tasks after successful processing
        task_manager.clear_pending_tasks(message.contact_urn)

        return dispatch(
            llm_response=response,
            message=message,
            direct_message=broadcast,
            user_email=flows_user_email,
            full_chunks=[],
        )

    except Exception as e:
        # Clean up Redis entries in case of error
        task_manager.clear_pending_tasks(message.contact_urn)

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
