import json
import logging
import os
from typing import Dict, Optional, Tuple

import boto3
import botocore
import elasticapm
import openai
import sentry_sdk
from django.conf import settings

from inline_agents.backends import BackendsRegistry
from nexus.celery import app as celery_app
from nexus.inline_agents.team.repository import ORMTeamRepository
from nexus.projects.websockets.consumers import send_preview_message_to_websocket
from nexus.usecases.inline_agents.typing import TypingUsecase
from nexus.usecases.intelligences.get_by_uuid import get_project_and_content_base_data
from router.dispatcher import dispatch
from router.entities import message_factory
from router.tasks.exceptions import EmptyFinalResponseException, EmptyTextException
from router.tasks.redis_task_manager import RedisTaskManager

from .actions_client import get_action_clients

logger = logging.getLogger(__name__)


def _apm_set_context(**kwargs):
    try:
        elasticapm.set_custom_context(kwargs)
    except:
        pass


def get_task_manager() -> RedisTaskManager:
    """Get the default task manager instance."""
    return RedisTaskManager()


def handle_attachments(text: str, attachments: list[str]) -> tuple[str, bool]:
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


def handle_overwrite_message(text: str, overwrite_message: dict | list | str) -> str:
    """
    Handles overwrite_message from metadata.
    If it's a dict/object, formats it with a label (like product_items).
    If it's a string, uses it as-is.
    """
    if isinstance(overwrite_message, (dict, list)):
        formatted = f"overwrite message: {str(overwrite_message)}"
    else:
        formatted = str(overwrite_message)

    return f"{text} {formatted}" if text else formatted


def complexity_layer(input_text: str) -> str | None:
    if input_text:
        try:
            payload = {"first_input": input_text}
            response = boto3.client("lambda", region_name=settings.AWS_BEDROCK_REGION_NAME).invoke(
                FunctionName=settings.COMPLEXITY_LAYER_LAMBDA,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload).encode("utf-8"),
            )

            if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                payload = json.loads(response["Payload"].read().decode("utf-8"))
                classification = payload.get("body").get("classification")
                logger.debug(
                    "Message classification",
                    extra={"text_len": len(input_text or ""), "classification": classification},
                )
                return classification
            else:
                error_msg = (
                    f"Lambda invocation failed with status code: {response['ResponseMetadata']['HTTPStatusCode']}"
                )
                sentry_sdk.set_context(
                    "extra_data",
                    {
                        "input_text": input_text,
                        "response": response,
                        "status_code": response["ResponseMetadata"]["HTTPStatusCode"],
                    },
                )
                sentry_sdk.capture_message(error_msg, level="error")
                raise Exception(error_msg)

        except Exception as e:
            sentry_sdk.set_context(
                "extra_data",
                {
                    "input_text": input_text,
                    "response": response if "response" in locals() else None,
                },
            )
            sentry_sdk.capture_exception(e)
            return None


def dispatch_preview(
    response: str, message_obj: Dict, broadcast: Dict, user_email: str, agents_backend: str, flows_user_email: str
) -> str:
    response_msg = dispatch(
        llm_response=response,
        message=message_obj,
        direct_message=broadcast,
        user_email=flows_user_email,
        full_chunks=[],
        backend=agents_backend,
    )
    send_preview_message_to_websocket(
        project_uuid=message_obj.project_uuid,
        user_email=user_email,
        message_data={"type": "preview", "content": response_msg},
    )
    return response_msg


def guardrails_complexity_layer(input_text: str, guardrail_id: str, guardrail_version: str) -> str | None:
    logger.debug(
        "Guardrails complexity layer",
        extra={"text_len": len(input_text or ""), "guardrail_id": guardrail_id, "guardrail_version": guardrail_version},
    )
    try:
        payload = {
            "first_input": input_text,
            "guardrail_id": guardrail_id,
            "guardrail_version": guardrail_version,
        }
        response = boto3.client("lambda", region_name=settings.AWS_BEDROCK_REGION_NAME).invoke(
            FunctionName=settings.GUARDRAILS_LAYER_LAMBDA,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode("utf-8"),
        )
        if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
            payload = json.loads(response["Payload"].read().decode("utf-8"))

            logger.debug("Guardrails complexity layer response", extra={"keys": list(payload.keys())})
            response = payload
            status_code = payload.get("statusCode")
            if status_code == 200:
                guardrails_message = response.get("body", {}).get("message")
                return guardrails_message
            else:
                return None

    except Exception as e:
        sentry_sdk.capture_exception(e)
        sentry_sdk.set_context(
            "extra_data",
            {
                "input_text": input_text,
                "guardrail_id": guardrail_id,
                "guardrail_version": guardrail_version,
            },
        )
        return None


class UnsafeMessageException(Exception):
    message: str

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


def _preprocess_message_input(message: Dict, backend: str) -> Tuple[Dict, Optional[str], bool]:
    """
    Handles complexity layer, attachments, and product items.
    """
    text = message.get("text", "")
    attachments = message.get("attachments", [])
    product_items = message.get("metadata", {}).get("order", {}).get("product_items", [])
    overwrite_message = message.get("metadata", {}).get("overwrite_message")
    foundation_model = None

    if backend == "BedrockBackend":
        foundation_model = complexity_layer(text)
    else:
        pass
        # guardrails: Dict[str, str] = GuardrailsUsecase.get_guardrail_as_dict(message.get("project_uuid"))
        # guardrails_message = guardrails_complexity_layer(
        #     text, guardrails.get("guardrailIdentifier"), guardrails.get("guardrailVersion")
        # )
        # if guardrails_message:
        #     raise UnsafeMessageException(guardrails_message)

    text, turn_off_rationale = handle_attachments(text=text, attachments=attachments)

    if len(product_items) > 0:
        text = handle_product_items(text, product_items)

    if not text.strip():
        raise EmptyTextException(
            f"Text is empty after processing. Original text: '{message.get('text', '')}', "
            f"attachments: {attachments}, product_items: {product_items}"
        )

    if overwrite_message:
        text = handle_overwrite_message(text, overwrite_message)

    processed_message = message.copy()
    processed_message["text"] = text
    return processed_message, foundation_model, turn_off_rationale


def _manage_pending_task(task_manager: RedisTaskManager, message_obj, current_task_id: str) -> str:
    """
    Handles revoking old tasks and concatenating messages for rapid inputs.
    """
    pending_task_id = task_manager.get_pending_task_id(message_obj.project_uuid, message_obj.contact_urn)
    if pending_task_id and pending_task_id != current_task_id:
        celery_app.control.revoke(pending_task_id, terminate=True)

    final_message_text = task_manager.handle_pending_response(
        project_uuid=message_obj.project_uuid, contact_urn=message_obj.contact_urn, message_text=message_obj.text
    )

    task_manager.store_pending_task_id(message_obj.project_uuid, message_obj.contact_urn, current_task_id)
    return final_message_text


def _handle_task_error(
    exc: Exception,
    task_manager: RedisTaskManager,
    message: Dict,
    task_id: str,
    preview: bool,
    language: str,
    user_email: str,
):
    """
    Centralized error handling for the Celery task.
    """
    project_uuid = message.get("project_uuid")
    contact_urn = message.get("contact_urn")

    sentry_sdk.set_context(
        "message",
        {
            "project_uuid": project_uuid,
            "contact_urn": contact_urn,
            "channel_uuid": message.get("channel_uuid"),
            "contact_name": message.get("contact_name"),
            "text": message.get("text", ""),
            "preview": preview,
            "language": language,
            "user_email": user_email,
            "task_id": task_id,
            "pending_task_id": task_manager.get_pending_task_id(project_uuid, contact_urn) if task_manager else None,
        },
    )
    sentry_sdk.set_tag("preview_mode", preview)
    sentry_sdk.set_tag("project_uuid", project_uuid)
    sentry_sdk.set_tag("task_id", task_id)
    sentry_sdk.set_tag("contact_urn", contact_urn)

    if task_manager:
        task_manager.clear_pending_tasks(project_uuid, contact_urn)

    logger.error("Error in start_inline_agents: %s", str(exc), exc_info=True)

    if isinstance(exc, botocore.exceptions.EventStreamError) and "throttlingException" in str(exc):
        raise ThrottlingException(str(exc))

    if user_email:
        send_preview_message_to_websocket(
            user_email=user_email, project_uuid=str(project_uuid), message_data={"type": "error", "content": str(exc)}
        )

    sentry_sdk.capture_exception(exc)
    raise exc


@celery_app.task(
    bind=True,
    soft_time_limit=300,
    time_limit=360,
    acks_late=settings.START_INLINE_AGENTS_ACK_LATE,
    autoretry_for=(ThrottlingException,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def start_inline_agents(
    self,
    message: Dict,
    preview: bool = False,
    language: str = "en",
    user_email: str = "",
    task_manager: Optional[RedisTaskManager] = None,
) -> bool:  # pragma: no cover
    _apm_set_context(message=message, preview=preview)

    task_manager = task_manager or get_task_manager()

    try:
        TypingUsecase().send_typing_message(
            contact_urn=message.get("contact_urn"),
            msg_external_id=message.get("msg_event", {}).get("msg_external_id", ""),
            project_uuid=message.get("project_uuid"),
            preview=preview,
        )

        project, content_base, inline_agent_configuration = get_project_and_content_base_data(
            message.get("project_uuid")
        )
        agents_backend = project.agents_backend

        broadcast, _ = get_action_clients(
            preview=preview, multi_agents=True, project_use_components=project.use_components
        )

        flows_user_email = os.environ.get("FLOW_USER_EMAIL")

        processed_message, foundation_model, turn_off_rationale = _preprocess_message_input(message, agents_backend)

        # TODO: Logs
        message_obj = message_factory(
            project_uuid=processed_message.get("project_uuid"),
            text=processed_message.get("text"),
            contact_urn=processed_message.get("contact_urn"),
            metadata=processed_message.get("metadata"),
            attachments=processed_message.get("attachments", []),
            msg_event=processed_message.get("msg_event"),
            contact_fields=processed_message.get("contact_fields", {}),
            contact_name=processed_message.get("contact_name", ""),
            channel_uuid=processed_message.get("channel_uuid", ""),
        )

        logger.debug("Message object built", extra={"has_text": bool(message_obj.text)})

        message_obj.text = _manage_pending_task(task_manager, message_obj, self.request.id)

        backend = BackendsRegistry.get_backend(agents_backend)
        team = ORMTeamRepository(agents_backend=agents_backend, project=project).get_team(message_obj.project_uuid)

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
            msg_external_id=processed_message.get("msg_event", {}).get("msg_external_id", ""),
            turn_off_rationale=turn_off_rationale,
            use_prompt_creation_configurations=project.use_prompt_creation_configurations,
            conversation_turns_to_include=project.conversation_turns_to_include,
            exclude_previous_thinking_steps=project.exclude_previous_thinking_steps,
            project=project,
            content_base=content_base,
            foundation_model=foundation_model,
            inline_agent_configuration=inline_agent_configuration,
        )

        if response is None or response == "":
            raise EmptyFinalResponseException("Final response is empty")

        task_manager.clear_pending_tasks(message_obj.project_uuid, message_obj.contact_urn)

        if preview:
            return dispatch_preview(response, message_obj, broadcast, user_email, agents_backend, flows_user_email)
        else:
            return dispatch(
                llm_response=response,
                message=message_obj,
                direct_message=broadcast,
                user_email=flows_user_email,
                full_chunks=[],
                backend=agents_backend,
            )

    except UnsafeMessageException as e:
        message_obj = message_factory(
            project_uuid=message.get("project_uuid"),
            text=message.get("text"),
            contact_urn=message.get("contact_urn"),
            metadata=message.get("metadata"),
            attachments=message.get("attachments", []),
            msg_event=message.get("msg_event"),
            contact_fields=message.get("contact_fields", {}),
            contact_name=message.get("contact_name", ""),
            channel_uuid=message.get("channel_uuid", ""),
        )
        if preview:
            return dispatch_preview(e.message, message_obj, broadcast, user_email, agents_backend, flows_user_email)
        return dispatch(
            llm_response=e.message,
            message=message_obj,
            direct_message=broadcast,
            user_email=flows_user_email,
            full_chunks=[],
            backend=agents_backend,
        )

    except (openai.APIError, EmptyFinalResponseException) as e:
        if self.request.retries < 2:
            task_manager.clear_pending_tasks(message_obj.project_uuid, message_obj.contact_urn)
            raise self.retry(
                exc=e,
                countdown=2**self.request.retries,
                max_retries=2,
                priority=0,
                jitter=False,
            ) from e
        _handle_task_error(e, task_manager, message, self.request.id, preview, language, user_email)
    except Exception as e:
        _handle_task_error(e, task_manager, message, self.request.id, preview, language, user_email)
