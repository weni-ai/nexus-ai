import os
from typing import Dict, Optional
import boto3
import json
import botocore
from django.conf import settings

import sentry_sdk
from inline_agents.backends import BackendsRegistry
from nexus.celery import app as celery_app
from nexus.inline_agents.team.repository import ORMTeamRepository
from nexus.projects.websockets.consumers import (
    send_preview_message_to_websocket,
)
from nexus.usecases.inline_agents.typing import TypingUsecase
from router.dispatcher import dispatch

from router.tasks.redis_task_manager import RedisTaskManager
from router.entities import message_factory
from router.tasks.exceptions import EmptyTextException

from .actions_client import get_action_clients
from nexus.usecases.intelligences.get_by_uuid import (
    get_project_and_content_base_data,
)


def get_task_manager() -> RedisTaskManager:
    """Get the default task manager instance."""
    return RedisTaskManager()


def handle_attachments(
    text: str,
    attachments: list[str]
) -> tuple[str, bool]:
    turn_off_rationale = False

    if attachments:
        if text:
            text = f"{text} {attachments}"
        else:
            turn_off_rationale = True
            text = str(attachments)

    return text, turn_off_rationale


class ThrottlingException(Exception):
    """Custom exception for AWS Bedrock throttling errors"""
    pass


def handle_product_items(text: str, product_items: list) -> str:
    if text:
        text = f"{text} product items: {str(product_items)}"
    else:
        text = f"product items: {str(product_items)}"
    return text


def complexity_layer(input_text: str) -> str | None:
    if input_text:
        try:
            payload = { "first_input": input_text }
            response = boto3.client("lambda", region_name=settings.AWS_BEDROCK_REGION_NAME).invoke(
                FunctionName=settings.COMPLEXITY_LAYER_LAMBDA,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload).encode("utf-8"),
            )

            if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                payload = json.loads(response['Payload'].read().decode('utf-8'))
                classification = payload.get("body").get("classification")
                print(f"[DEBUG] Message: {input_text} - Classification: {classification}")
                return classification
            else:
                error_msg = f"Lambda invocation failed with status code: {response['ResponseMetadata']['HTTPStatusCode']}"
                sentry_sdk.set_context("extra_data", {
                    "input_text": input_text,
                    "response": response,
                    "status_code": response["ResponseMetadata"]["HTTPStatusCode"]
                })
                sentry_sdk.capture_message(error_msg, level="error")
                raise Exception(error_msg)

        except Exception as e:
            sentry_sdk.set_context("extra_data", {
                "input_text": input_text,
                "response": response if 'response' in locals() else None,
            })
            sentry_sdk.capture_exception(e)
            return None


@celery_app.task(
    bind=True,
    soft_time_limit=300,
    time_limit=360,
    acks_late=settings.START_INLINE_AGENTS_ACK_LATE,
    autoretry_for=(ThrottlingException,),
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
    user_email: str = '',
    task_manager: Optional[RedisTaskManager] = None
) -> bool:  # pragma: no cover

    try:

        task_manager = task_manager or get_task_manager()

        text = message.get("text", "")
        attachments = message.get("attachments", [])
        message_event = message.get("msg_event", {})
        product_items = message.get("metadata", {}).get("order", {}).get("product_items", [])

        typing_usecase = TypingUsecase()
        typing_usecase.send_typing_message(
            contact_urn=message.get("contact_urn"),
            msg_external_id=message_event.get("msg_external_id", ""),
            project_uuid=message.get("project_uuid"),
            preview=preview
        )

        foundation_model = complexity_layer(text)

        text, turn_off_rationale = handle_attachments(
            text=text,
            attachments=attachments
        )

        if len(product_items) > 0:
            text = handle_product_items(text, product_items)

        if not text.strip():
            raise EmptyTextException(
                f"Text is empty after processing. Original text: '{message.get('text', '')}', "
                f"attachments: {attachments}, product_items: {product_items}"
            )

        # Update the original message dict with processed text
        message['text'] = text

        # TODO: Logs
        message_obj = message_factory(
            project_uuid=message.get("project_uuid"),
            text=text,
            contact_urn=message.get("contact_urn"),
            metadata=message.get("metadata"),
            attachments=attachments,
            msg_event=message.get("msg_event"),
            contact_fields=message.get("contact_fields", {}),
            contact_name=message.get("contact_name", ""),
            channel_uuid=message.get("channel_uuid", ""),
        )

        print(f"[DEBUG] Message: {message_obj}")

        project, content_base = get_project_and_content_base_data(message_obj.project_uuid)

        pending_task_id = task_manager.get_pending_task_id(message_obj.project_uuid, message_obj.contact_urn)
        if pending_task_id:
            celery_app.control.revoke(pending_task_id, terminate=True)

        final_message_text = task_manager.handle_pending_response(message_obj.project_uuid, message_obj.contact_urn, message_obj.text)
        message_obj.text = final_message_text

        task_manager.store_pending_task_id(message_obj.project_uuid, message_obj.contact_urn, self.request.id)

        if user_email:
            send_preview_message_to_websocket(
                project_uuid=message_obj.project_uuid,
                user_email=user_email,
                message_data={
                    "type": "status",
                    "content": "Starting multi-agent processing",
                    # "session_id": session_id # TODO: add session_id
                }
            )

        project_use_components = project.use_components

        broadcast, _ = get_action_clients(
            preview=preview,
            multi_agents=True,
            project_use_components=project_use_components
        )

        flows_user_email = os.environ.get("FLOW_USER_EMAIL")

        agents_backend = project.agents_backend
        backend = BackendsRegistry.get_backend(agents_backend)

        rep = ORMTeamRepository()
        team = rep.get_team(message_obj.project_uuid)

        response = backend.invoke_agents(
            team=team,
            input_text=message_obj.text,
            contact_urn=message_obj.contact_urn,
            project_uuid=message_obj.project_uuid,
            preview=preview,
            rationale_switch=project.rationale_switch,
            sanitized_urn=message_obj.sanitized_urn,
            language=language,
            user_email=user_email,
            use_components=project.use_components,
            contact_fields=message_obj.contact_fields_as_json,
            contact_name=message_obj.contact_name,
            channel_uuid=message_obj.channel_uuid,
            msg_external_id=message_event.get("msg_external_id", ""),
            turn_off_rationale=turn_off_rationale,
            use_prompt_creation_configurations=project.use_prompt_creation_configurations,
            conversation_turns_to_include=project.conversation_turns_to_include,
            exclude_previous_thinking_steps=project.exclude_previous_thinking_steps,
            project=project,
            content_base=content_base,
            foundation_model=foundation_model,
        )

        task_manager.clear_pending_tasks(message_obj.project_uuid, message_obj.contact_urn)

        if preview:
            response_msg = dispatch(
                llm_response=response,
                message=message_obj,
                direct_message=broadcast,
                user_email=flows_user_email,
                full_chunks=[],
            )
            send_preview_message_to_websocket(
                project_uuid=message_obj.project_uuid,
                user_email=user_email,
                message_data={
                    "type": "preview",
                    "content": response_msg
                }
            )
            return response_msg

        return dispatch(
            llm_response=response,
            message=message_obj,
            direct_message=broadcast,
            user_email=flows_user_email,
            full_chunks=[],
        )

    except Exception as e:
        # Set Sentry context with relevant information
        sentry_sdk.set_context("message", {
            "project_uuid": message.get("project_uuid"),
            "contact_urn": message.get("contact_urn"),
            "channel_uuid": message.get("channel_uuid"),
            "contact_name": message.get("contact_name"),
            "text": message.get("text", ""),
            "preview": preview,
            "language": language,
            "user_email": user_email,
            "task_id": self.request.id,
            "pending_task_id": task_manager.get_pending_task_id(message.get("project_uuid"), message.get("contact_urn")) if task_manager else None,
        })

        # Add tags for better filtering in Sentry
        sentry_sdk.set_tag("preview_mode", preview)
        sentry_sdk.set_tag("project_uuid", message.get("project_uuid"))
        sentry_sdk.set_tag("task_id", self.request.id)
        sentry_sdk.set_tag("contact_urn", message.get("contact_urn"))

        # Clean up Redis entries in case of error
        if task_manager:
            task_manager.clear_pending_tasks(message.get("project_uuid"), message.get("contact_urn"))

        print(f"[DEBUG] Error in start_inline_agents: {str(e)}")
        print(f"[DEBUG] Error type: {type(e)}")
        print(f"[DEBUG] Full exception details: {e.__dict__}")

        if isinstance(e, botocore.exceptions.EventStreamError) and 'throttlingException' in str(e):
            raise ThrottlingException(str(e))

        if user_email:
            send_preview_message_to_websocket(
                user_email=user_email,
                project_uuid=str(message.get("project_uuid")),
                message_data={
                    "type": "error",
                    "content": str(e),
                    # "session_id": session_id TODO: add session_id
                }
            )

        # Capture the exception in Sentry with all the context
        sentry_sdk.capture_exception(e)
        raise
