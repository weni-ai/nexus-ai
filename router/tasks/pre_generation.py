import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple

import sentry_sdk

from inline_agents.backends.openai.redis_pool import get_redis_client
from nexus.celery import app as celery_app
from router.entities import message_factory
from router.services.pre_generation_service import PreGenerationService
from router.tasks.invocation_context import CachedProjectData
from router.tasks.invoke import (
    EmptyTextException,
    handle_attachments,
    handle_overwrite_message,
    handle_product_items,
)
from router.tasks.redis_task_manager import RedisTaskManager

logger = logging.getLogger(__name__)


@dataclass
class PreGenerationDependencies:

    data_service: PreGenerationService = field(default_factory=PreGenerationService)
    task_manager: RedisTaskManager = field(
        default_factory=lambda: RedisTaskManager(redis_client=get_redis_client())
    )
    fetch_credentials: Callable[[str], dict] = field(default=None)
    ensure_conversation: Callable[..., Optional[str]] = field(default=None)
    generate_auth_token: Callable[[str], str] = field(default=None)
    save_user_message: Callable[..., None] = field(default=None)

    def __post_init__(self):
        if self.fetch_credentials is None:
            self.fetch_credentials = _default_fetch_credentials
        if self.ensure_conversation is None:
            self.ensure_conversation = _default_ensure_conversation
        if self.generate_auth_token is None:
            self.generate_auth_token = _default_generate_auth_token
        if self.save_user_message is None:
            self.save_user_message = _default_save_user_message


def _default_fetch_credentials(project_uuid: str) -> dict:
    from nexus.inline_agents.models import AgentCredential

    agent_credentials = AgentCredential.objects.filter(project_id=project_uuid)
    credentials = {}
    for credential in agent_credentials:
        credentials[credential.key] = credential.decrypted_value
    return credentials


def _default_ensure_conversation(
    project_uuid: str,
    contact_urn: str,
    contact_name: str,
    channel_uuid: str,
    preview: bool = False,
) -> Optional[str]:
    if preview:
        return None

    if not channel_uuid:
        sentry_sdk.set_tag("project_uuid", project_uuid)
        sentry_sdk.set_tag("contact_urn", contact_urn)
        sentry_sdk.set_context(
            "conversation_creation",
            {
                "project_uuid": project_uuid,
                "contact_urn": contact_urn,
                "contact_name": contact_name,
                "channel_uuid": None,
                "reason": "channel_uuid is None",
            },
        )
        sentry_sdk.capture_message("Conversation not created: channel_uuid is None (pre-generation)", level="warning")
        return None

    try:
        from router.services.conversation_service import ConversationService

        conversation_service = ConversationService()
        conversation = conversation_service.ensure_conversation_exists(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            contact_name=contact_name,
            channel_uuid=channel_uuid,
        )
        return str(conversation.uuid) if conversation else None
    except Exception as e:
        sentry_sdk.set_tag("project_uuid", project_uuid)
        sentry_sdk.set_tag("contact_urn", contact_urn)
        sentry_sdk.set_tag("channel_uuid", channel_uuid)
        sentry_sdk.set_context(
            "conversation_creation",
            {
                "project_uuid": project_uuid,
                "contact_urn": contact_urn,
                "contact_name": contact_name,
                "channel_uuid": channel_uuid,
                "error": str(e),
            },
        )
        sentry_sdk.capture_exception(e)
        return None


def _default_generate_auth_token(project_uuid: str) -> str:
    from nexus.usecases.jwt.jwt_usecase import JWTUsecase

    jwt_usecase = JWTUsecase()
    return jwt_usecase.generate_jwt_token(project_uuid)


def _default_save_user_message(
    project_uuid: str,
    contact_urn: str,
    input_text: str,
    preview: bool,
    session_id: str,
    contact_name: str,
    channel_uuid: str,
) -> None:
    from router.traces_observers.save_traces import save_inline_message_async

    save_inline_message_async.delay(
        project_uuid=project_uuid,
        contact_urn=contact_urn,
        text=input_text,
        preview=preview,
        session_id=session_id,
        source_type="user",
        contact_name=contact_name,
        channel_uuid=channel_uuid,
    )


def preprocess_message(message: Dict) -> Tuple[Dict, bool]:
    text = message.get("text", "")
    attachments = message.get("attachments", [])
    product_items = message.get("metadata", {}).get("order", {}).get("product_items", [])
    overwrite_message = message.get("metadata", {}).get("overwrite_message")

    text, turn_off_rationale = handle_attachments(text=text, attachments=attachments)

    if len(product_items) > 0:
        text = handle_product_items(text, product_items)

    if overwrite_message:
        text = handle_overwrite_message(text, overwrite_message)

    if not text.strip():
        raise EmptyTextException(
            f"Text is empty after processing. Original text: '{message.get('text', '')}', "
            f"attachments: {attachments}, product_items: {product_items}"
        )

    processed_message = message.copy()
    processed_message["text"] = text
    return processed_message, turn_off_rationale


def compute_session_id(project_uuid: str, sanitized_urn: str) -> str:
    return f"project-{project_uuid}-session-{sanitized_urn}"


def build_invoke_kwargs(
    cached_data: CachedProjectData,
    message: Dict,
    preview: bool,
    language: str,
    user_email: str,
    turn_off_rationale: bool,
    credentials: Optional[dict] = None,
    auth_token: Optional[str] = None,
    session_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> Dict:
    invoke_kwargs = cached_data.get_invoke_kwargs(team=cached_data.team)

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

    invoke_kwargs.update(
        {
            "input_text": message_obj.text,
            "contact_urn": message_obj.contact_urn,
            "project_uuid": message_obj.project_uuid,
            "sanitized_urn": message_obj.sanitized_urn,
            "contact_fields": message_obj.contact_fields_as_json,
            "contact_name": message_obj.contact_name,
            "channel_uuid": message_obj.channel_uuid,
            "msg_external_id": message.get("msg_event", {}).get("msg_external_id", ""),
            "preview": preview,
            "language": language,
            "user_email": user_email,
            "foundation_model": None,
            "turn_off_rationale": turn_off_rationale,
            "channel_type": message.get("channel_type", ""),
        }
    )

    if credentials is not None:
        invoke_kwargs["_pre_fetched_credentials"] = credentials
    if auth_token is not None:
        invoke_kwargs["_pre_fetched_auth_token"] = auth_token
    if session_id is not None:
        invoke_kwargs["_pre_fetched_session_id"] = session_id
    if conversation_id is not None:
        invoke_kwargs["_pre_fetched_conversation_id"] = conversation_id

    return invoke_kwargs


class PreGenerationExecutor:
    """Executes pre-generation logic with injectable dependencies."""

    def __init__(self, deps: PreGenerationDependencies = None):
        self.deps = deps or PreGenerationDependencies()

    def execute(
        self,
        message: Dict,
        preview: bool = False,
        language: str = "en",
        user_email: str = "",
        workflow_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Dict:
        project_uuid = message.get("project_uuid")
        contact_urn = message.get("contact_urn")
        contact_name = message.get("contact_name", "")
        channel_uuid = message.get("channel_uuid", "")

        if workflow_id and contact_urn:
            self.deps.task_manager.update_workflow_status(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                status="pre_generation",
                task_phase="pre_generation",
                task_id=task_id,
            )

        try:
            return self._execute_core(
                message=message,
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                contact_name=contact_name,
                channel_uuid=channel_uuid,
                preview=preview,
                language=language,
                user_email=user_email,
                workflow_id=workflow_id,
            )
        except Exception as e:
            logger.error(f"[PreGeneration] Failed for project {project_uuid}, contact {contact_urn}: {e}", exc_info=True)
            sentry_sdk.capture_exception(e)

            if workflow_id and contact_urn:
                self.deps.task_manager.update_workflow_status(
                    project_uuid=project_uuid,
                    contact_urn=contact_urn,
                    status="failed",
                )

            return {
                "status": "failed",
                "error": str(e),
                "project_uuid": project_uuid,
                "workflow_id": workflow_id,
            }

    def _execute_core(
        self,
        message: Dict,
        project_uuid: str,
        contact_urn: str,
        contact_name: str,
        channel_uuid: str,
        preview: bool,
        language: str,
        user_email: str,
        workflow_id: Optional[str],
    ) -> Dict:
        # Fetch project data
        (
            project_dict,
            content_base_dict,
            team,
            guardrails_config,
            inline_agent_config,
            agents_backend,
            instructions,
            agent_data,
        ) = self.deps.data_service.fetch_pre_generation_data(project_uuid)

        # Preprocess message (pure function)
        processed_message, turn_off_rationale = preprocess_message(message)

        # Build cached data
        cached_data = CachedProjectData.from_pre_generation_data(
            project_dict=project_dict,
            content_base_dict=content_base_dict,
            team=team,
            guardrails_config=guardrails_config,
            inline_agent_config_dict=inline_agent_config,
            instructions=instructions,
            agent_data=agent_data,
        )

        # Create message object for sanitized_urn
        message_obj = message_factory(
            project_uuid=project_uuid,
            text=processed_message.get("text"),
            contact_urn=contact_urn,
            metadata=message.get("metadata"),
            attachments=message.get("attachments", []),
            msg_event=message.get("msg_event"),
            contact_fields=message.get("contact_fields", {}),
            contact_name=contact_name,
            channel_uuid=channel_uuid,
        )

        # Pre-fetch data using injected dependencies
        credentials = self.deps.fetch_credentials(project_uuid)

        conversation_id = self.deps.ensure_conversation(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            contact_name=contact_name,
            channel_uuid=channel_uuid,
            preview=preview,
        )

        auth_token = self.deps.generate_auth_token(project_uuid)
        session_id = compute_session_id(project_uuid, message_obj.sanitized_urn)

        self.deps.save_user_message(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            input_text=processed_message.get("text"),
            preview=preview,
            session_id=session_id,
            contact_name=contact_name,
            channel_uuid=channel_uuid,
        )

        # Build invoke_kwargs (pure function)
        invoke_kwargs = build_invoke_kwargs(
            cached_data=cached_data,
            message=processed_message,
            preview=preview,
            language=language,
            user_email=user_email,
            turn_off_rationale=turn_off_rationale,
            credentials=credentials,
            auth_token=auth_token,
            session_id=session_id,
            conversation_id=conversation_id,
        )

        logger.info(f"[PreGeneration] Success for project {project_uuid}, contact {contact_urn}")

        return {
            "status": "success",
            "invoke_kwargs": invoke_kwargs,
            "cached_data": cached_data.to_dict(),
            "agents_backend": agents_backend,
            "processed_message": processed_message,
            "project_uuid": project_uuid,
            "workflow_id": workflow_id,
            "use_components": project_dict.get("use_components", False),
            "pre_fetched": {
                "credentials_count": len(credentials),
                "auth_token_generated": bool(auth_token),
                "session_id": session_id,
                "conversation_id": conversation_id,
            },
        }


@celery_app.task(
    bind=True,
    name="router.tasks.pre_generation.pre_generation_task",
    soft_time_limit=60,
    time_limit=90,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=30,
)
def pre_generation_task(
    self,
    message: Dict,
    preview: bool = False,
    language: str = "en",
    user_email: str = "",
    workflow_id: Optional[str] = None,
) -> Dict:
    executor = PreGenerationExecutor()
    return executor.execute(
        message=message,
        preview=preview,
        language=language,
        user_email=user_email,
        workflow_id=workflow_id,
        task_id=self.request.id,
    )


def deserialize_cached_data(serialized_data: Dict) -> CachedProjectData:
    return CachedProjectData(
        project_dict=serialized_data.get("project_dict"),
        content_base_dict=serialized_data.get("content_base_dict"),
        team=serialized_data.get("team"),
        guardrails_config=serialized_data.get("guardrails_config"),
        inline_agent_config_dict=serialized_data.get("inline_agent_config_dict"),
        instructions=serialized_data.get("instructions"),
        agent_data=serialized_data.get("agent_data"),
        formatter_agent_configurations=serialized_data.get("formatter_agent_configurations"),
    )
