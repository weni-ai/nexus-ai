import json
import logging
import re
from typing import Optional, Tuple, Union

import pendulum
from weni.eda.connection import EDAConnection
from weni_commons.change_history import Action, Entity, Module, Notifier

from nexus.logs.models import RecentActivities

from .publishers_dto import RecentActivitiesDTO

logger = logging.getLogger(__name__)

ACTION_TYPE_TO_ACTION = {
    "C": Action.CREATE,
    "U": Action.UPDATE,
    "D": Action.DELETE,
    "CREATE": Action.CREATE,
    "UPDATE": Action.UPDATE,
    "DELETE": Action.DELETE,
    "ADD": Action.ADD,
}

ACTION_MODEL_TO_ENTITY = {
    "Flow": Entity.FLOW,
    "ContentBase": Entity.CONTENT_BASE,
    "ContentBaseAgent": Entity.CONTENT_BASE_AGENT,
    "ContentBaseFile": Entity.CONTENT_BASE_FILE,
    "ContentBaseInstruction": Entity.CONTENT_BASE_INSTRUCTION,
    "ContentBaseLink": Entity.CONTENT_BASE_LINK,
    "ContentBaseText": Entity.CONTENT_BASE_TEXT,
    "Intelligence": Entity.INTELLIGENCE,
    "LLM": Entity.LLM,
    "Project": Entity.PROJECT,
    "brain_on": Entity.PROJECT,
}


def _resolve_action(action: str) -> Action:
    resolved = ACTION_TYPE_TO_ACTION.get(action)
    if resolved is not None:
        return resolved
    try:
        return Action(action)
    except ValueError:
        logger.warning("Unknown change-history action %r, defaulting to UPDATE", action)
        return Action.UPDATE


def _pascal_to_screaming_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()


def _resolve_entity(action_model: Optional[Union[str, Entity]]) -> Entity:
    if isinstance(action_model, Entity):
        return action_model
    if not action_model:
        logger.warning("Missing change-history entity, defaulting to PROJECT")
        return Entity.PROJECT

    mapped = ACTION_MODEL_TO_ENTITY.get(action_model)
    if mapped is not None:
        return mapped

    try:
        return Entity(action_model)
    except ValueError:
        pass

    try:
        return Entity(_pascal_to_screaming_snake(action_model))
    except ValueError:
        logger.warning(
            "Unknown change-history entity %r, defaulting to PROJECT",
            action_model,
        )
        return Entity.PROJECT


def _values_from_details(action_details: Optional[dict]) -> Tuple[Optional[str], Optional[str]]:
    if not action_details:
        return None, None

    if len(action_details) == 1:
        change = next(iter(action_details.values()))
        if isinstance(change, dict) and "old" in change and "new" in change:
            return str(change["old"]), str(change["new"])

    return None, json.dumps(action_details)


# Human-readable label for change-history object_name (not the Django class name).
_OBJECT_NAME_ATTRS_BY_MODEL = {
    "ContentBaseLink": ("link", "name"),
    "ContentBaseFile": ("file_name", "created_file_name"),
    "ContentBaseText": ("title", "file_name"),
    "ContentBaseInstruction": ("instruction", "suggested_category"),
    "ContentBaseAgent": ("name",),
    "ContentBase": ("title",),
    "Intelligence": ("name",),
    "LLM": ("model",),
    "Flow": ("name",),
    "Project": ("name",),
}


def _object_name_from_instance(instance) -> Optional[str]:
    if instance is None:
        return None

    model_name = instance.__class__.__name__
    for attr in _OBJECT_NAME_ATTRS_BY_MODEL.get(model_name, ("name", "title", "link", "file_name")):
        try:
            value = getattr(instance, attr, None)
            if callable(value):
                value = value()
        except Exception:
            continue
        if value is None:
            continue
        text = str(value).strip()
        if text:
            # Keep instruction labels short for the activity feed.
            if attr == "instruction" and len(text) > 120:
                return f"{text[:117]}..."
            return text

    return None


def _object_id_from_instance(instance, *, fallback: str) -> str:
    if instance is None:
        return fallback
    if getattr(instance, "uuid", None) is not None:
        return str(instance.uuid)
    pk = getattr(instance, "pk", None)
    if pk is not None:
        return str(pk)
    return fallback


def notify_change(
    *,
    project_uuid: str,
    user_email: str,
    date: pendulum.DateTime,
    action: str,
    entity: Optional[Union[str, Entity]] = None,
    object_id: Optional[str] = None,
    object_name: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    user_ip: Optional[str] = None,
) -> None:
    """
    Publish change history via weni-commons Notifier (Amazon MQ).

    `entity` is the object type being changed (ContentBase, Intelligence, …).
    `object_name` is the concrete resource name when available.
    """
    if not project_uuid:
        logger.warning("Skipping change-history AMQ publish: missing project_uuid")
        return

    try:
        Notifier.notify_change(
            project_uuid=project_uuid,
            user_email=user_email,
            date=date,
            action=_resolve_action(action),
            entity=_resolve_entity(entity),
            module=Module.NEXUS,
            object_id=object_id,
            object_name=object_name,
            old_value=old_value,
            new_value=new_value,
            user_ip=user_ip,
        )
    except Exception:
        logger.exception("Failed to publish change history to Amazon MQ")
    finally:
        # Avoid leaking thread-local AMQP connections across Django tests.
        EDAConnection.clear_connection()


def publish_recent_activity_to_amq(*, recent_activity: RecentActivities, instance=None) -> None:
    old_value, new_value = _values_from_details(recent_activity.action_details)
    object_name = _object_name_from_instance(instance) or recent_activity.action_model
    object_id = _object_id_from_instance(instance, fallback=str(recent_activity.uuid))
    notify_change(
        project_uuid=str(recent_activity.project.uuid),
        user_email=recent_activity.created_by.email,
        date=pendulum.instance(recent_activity.created_at),
        action=recent_activity.action_type,
        entity=recent_activity.action_model,
        object_id=object_id,
        object_name=object_name,
        old_value=old_value,
        new_value=new_value,
    )


def publish_external_recent_activity_to_amq(dto: RecentActivitiesDTO) -> None:
    """
    Org-level recent activity messages have no single project on the DTO.
    Publish one change-history event per project in the org (same fan-out as create).
    """
    projects = list(dto.org.projects.all())
    if not projects:
        logger.warning(
            "Skipping change-history AMQ publish: org %s has no projects",
            getattr(dto.org, "uuid", None),
        )
        return

    now = pendulum.now("UTC")
    for project in projects:
        notify_change(
            project_uuid=str(project.uuid),
            user_email=dto.user.email,
            date=now,
            action=dto.action,
            entity=dto.action_model,
            object_name=dto.entity_name,
        )


def publish_brain_status_to_amq(*, user: str, project_uuid: str, brain_on: bool) -> None:
    notify_change(
        project_uuid=project_uuid,
        user_email=user,
        date=pendulum.now("UTC"),
        action="UPDATE",
        entity="brain_on",
        object_id=project_uuid,
        object_name="brain_on",
        old_value=str(not brain_on),
        new_value=str(brain_on),
    )
