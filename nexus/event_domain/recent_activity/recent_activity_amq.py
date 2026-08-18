import json
import logging
import re
from typing import Optional, Tuple, Union

import pendulum
from django.conf import settings
from django.db import transaction
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
    "Agent": Entity.AGENT,
    "Intelligence": Entity.INTELLIGENCE,
    "LLM": Entity.LLM,
    "Project": Entity.PROJECT,
    "brain_on": Entity.PROJECT,
}

ENTITY_TO_MODULE = {
    Entity.CONTENT_BASE: Module.KNOWLEDGE_BASE,
    Entity.CONTENT_BASE_FILE: Module.KNOWLEDGE_BASE,
    Entity.CONTENT_BASE_LINK: Module.KNOWLEDGE_BASE,
    Entity.CONTENT_BASE_TEXT: Module.KNOWLEDGE_BASE,
    Entity.CONTENT_BASE_INSTRUCTION: Module.INSTRUCTIONS,
    Entity.CONTENT_BASE_AGENT: Module.MY_AGENTS,
    Entity.AGENT: Module.MY_AGENTS,
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


def _resolve_module(entity: Entity) -> Module:
    return ENTITY_TO_MODULE.get(entity, Module.NEXUS)


_ACTION_DETAILS_SKIP_KEYS = frozenset(
    {
        "modified_at",
        "modified_by",
        "created_at",
        "created_by",
        "last_updated_at",
        "end_at",
        "uuid",
        "id",
        "pk",
    }
)

_ACTION_DETAILS_PREFERRED_KEYS = (
    "text",
    "instruction",
    "link",
    "name",
    "title",
    "file_name",
    "created_file_name",
    "goal",
    "role",
    "personality",
    "brain_on",
)


def _stringify_change_value(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def _pair_from_change(change) -> Optional[Tuple[Optional[str], Optional[str]]]:
    if isinstance(change, dict) and "old" in change and "new" in change:
        return _stringify_change_value(change["old"]), _stringify_change_value(change["new"])
    return None


def _values_from_details(action_details: Optional[dict]) -> Tuple[Optional[str], Optional[str]]:
    if not action_details:
        return None, None

    if (
        "old" in action_details
        and "new" in action_details
        and not any(isinstance(v, dict) and "old" in v and "new" in v for v in action_details.values())
    ):
        return _stringify_change_value(action_details["old"]), _stringify_change_value(action_details["new"])

    nested_changes = {
        key: change
        for key, change in action_details.items()
        if isinstance(change, dict) and "old" in change and "new" in change
    }

    if not nested_changes:
        logger.warning(
            "action_details has unexpected shape; falling back to json dump (keys=%s)",
            list(action_details.keys()),
        )
        return None, json.dumps(action_details)

    if len(nested_changes) == 1:
        return _pair_from_change(next(iter(nested_changes.values())))

    for preferred in _ACTION_DETAILS_PREFERRED_KEYS:
        if preferred in nested_changes:
            return _pair_from_change(nested_changes[preferred])

    content_changes = {k: v for k, v in nested_changes.items() if k not in _ACTION_DETAILS_SKIP_KEYS}
    if len(content_changes) == 1:
        return _pair_from_change(next(iter(content_changes.values())))
    if content_changes:
        return _pair_from_change(next(iter(content_changes.values())))

    logger.warning(
        "action_details has %d keys with only metadata changes; cannot extract content old/new",
        len(action_details),
    )
    return None, json.dumps(action_details)


# Human-readable label for change-history object_name (not the Django class name).
_OBJECT_NAME_ATTRS_BY_MODEL = {
    "ContentBaseLink": ("link", "name"),
    "ContentBaseFile": ("file_name", "created_file_name"),
    "ContentBaseText": ("title", "file_name"),
    "ContentBaseInstruction": ("instruction", "suggested_category"),
    "ContentBaseAgent": ("name",),
    "Agent": ("name",),
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
        except Exception as exc:
            logger.debug("Error reading attr %r from %r: %s", attr, instance, exc)
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
        resolved_entity = _resolve_entity(entity)
        Notifier.notify_change(
            project_uuid=project_uuid,
            user_email=user_email,
            date=date,
            action=_resolve_action(action),
            entity=resolved_entity,
            module=_resolve_module(resolved_entity),
            object_id=object_id,
            object_name=object_name,
            old_value=old_value,
            new_value=new_value,
            user_ip=user_ip,
        )
    except Exception:
        logger.exception("Failed to publish change history to Amazon MQ")
    finally:
        if getattr(settings, "TESTING", False):
            # Avoid leaking thread-local AMQP connections across Django tests.
            EDAConnection.clear_connection()


def _serialize_entity(entity: Optional[Union[str, Entity]]) -> Optional[str]:
    if entity is None:
        return None
    if isinstance(entity, Entity):
        return entity.value
    return str(entity)


def _enqueue_on_commit(enqueue_fn) -> None:
    if getattr(settings, "TESTING", False):
        enqueue_fn()
        return
    transaction.on_commit(enqueue_fn)


def schedule_notify_change(
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
    """Enqueue change-history publishing on Celery so AMQ I/O stays out of consumer pods."""
    if not getattr(settings, "USE_EDA", False):
        return

    from nexus.event_domain.recent_activity.tasks import notify_change_task

    payload = {
        "project_uuid": project_uuid,
        "user_email": user_email,
        "date_iso": date.isoformat(),
        "action": action,
        "entity": _serialize_entity(entity),
        "object_id": object_id,
        "object_name": object_name,
        "old_value": old_value,
        "new_value": new_value,
        "user_ip": user_ip,
    }

    def enqueue() -> None:
        notify_change_task.delay(**payload)

    _enqueue_on_commit(enqueue)


def publish_recent_activity_to_amq_sync(
    *,
    recent_activity: RecentActivities,
    object_name: Optional[str] = None,
    object_id: Optional[str] = None,
    instance=None,
) -> None:
    if instance is not None:
        object_name = _object_name_from_instance(instance) or object_name
        object_id = _object_id_from_instance(instance, fallback=object_id or str(recent_activity.uuid))

    old_value, new_value = _values_from_details(recent_activity.action_details)
    notify_change(
        project_uuid=str(recent_activity.project.uuid),
        user_email=recent_activity.created_by.email,
        date=pendulum.instance(recent_activity.created_at),
        action=recent_activity.action_type,
        entity=recent_activity.action_model,
        object_id=object_id or _object_id_from_instance(None, fallback=str(recent_activity.uuid)),
        object_name=object_name or recent_activity.action_model,
        old_value=old_value,
        new_value=new_value,
    )


def publish_recent_activity_to_amq(*, recent_activity: RecentActivities, instance=None) -> None:
    if not getattr(settings, "USE_EDA", False):
        return

    from nexus.event_domain.recent_activity.tasks import publish_recent_activity_task

    object_name = _object_name_from_instance(instance) or recent_activity.action_model
    object_id = _object_id_from_instance(instance, fallback=str(recent_activity.uuid))

    def enqueue() -> None:
        publish_recent_activity_task.delay(
            str(recent_activity.uuid),
            object_name,
            object_id,
        )

    _enqueue_on_commit(enqueue)


def publish_external_recent_activity_to_amq_sync(dto: RecentActivitiesDTO) -> None:
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


def publish_external_recent_activity_to_amq(dto: RecentActivitiesDTO) -> None:
    if not getattr(settings, "USE_EDA", False):
        return

    from nexus.event_domain.recent_activity.tasks import publish_external_recent_activity_task

    def enqueue() -> None:
        publish_external_recent_activity_task.delay(
            str(dto.org.uuid),
            dto.user.email,
            dto.entity_name,
            dto.action,
            dto.action_model,
        )

    _enqueue_on_commit(enqueue)


def publish_brain_status_to_amq(*, user: str, project_uuid: str, brain_on: bool, old_brain_on: bool) -> None:
    schedule_notify_change(
        project_uuid=project_uuid,
        user_email=user,
        date=pendulum.now("UTC"),
        action="UPDATE",
        entity="brain_on",
        object_id=project_uuid,
        object_name="brain_on",
        old_value=str(old_brain_on),
        new_value=str(brain_on),
    )
