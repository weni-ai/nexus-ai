from typing import Dict, Optional

from inline_agents.backends.openai.backend_calling import OpenAICallingBackend
from nexus.inline_agents.team.repository import ORMTeamRepository
from nexus.usecases.intelligences.get_by_uuid import (
    get_project_and_content_base_data,
)
from router.entities import message_factory
from router.tasks.exceptions import EmptyTextException
from router.tasks.invoke import (
    complexity_layer,
    handle_attachments,
    handle_product_items,
)
from router.tasks.redis_task_manager import RedisTaskManager


def get_task_manager() -> RedisTaskManager:
    """Get the default task manager instance."""
    return RedisTaskManager()


def get_calling_agents(
    message: Dict,
    preview: bool = False,
    language: str = "en",
    user_email: str = "",
    task_manager: Optional[RedisTaskManager] = None,
) -> bool:  # pragma: no cover

    text = message.get("text", "")
    attachments = message.get("attachments", [])
    message_event = message.get("msg_event", {})
    product_items = message.get("metadata", {}).get("order", {}).get("product_items", [])

    foundation_model = complexity_layer(text)

    text, turn_off_rationale = handle_attachments(text=text, attachments=attachments)

    if len(product_items) > 0:
        text = handle_product_items(text, product_items)

    if not text.strip():
        raise EmptyTextException(
            f"Text is empty after processing. Original text: '{message.get('text', '')}', "
            f"attachments: {attachments}, product_items: {product_items}"
        )

    message["text"] = text

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

    project, content_base, inline_agent_configuration = get_project_and_content_base_data(message_obj.project_uuid)

    message_obj.text = ""

    agents_backend = project.agents_backend

    rep = ORMTeamRepository(agents_backend=agents_backend, project=project)
    team = rep.get_team(message_obj.project_uuid)

    return OpenAICallingBackend().invoke_agents(
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
        inline_agent_configuration=inline_agent_configuration,
    )
