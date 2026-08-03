import json
import logging
from typing import Optional, Tuple

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


def _resolve_action(action: str) -> Action:
    resolved = ACTION_TYPE_TO_ACTION.get(action)
    if resolved is not None:
        return resolved
    try:
        return Action(action)
    except ValueError:
        logger.warning("Unknown change-history action %r, defaulting to UPDATE", action)
        return Action.UPDATE


def _values_from_details(action_details: Optional[dict]) -> Tuple[Optional[str], Optional[str]]:
    if not action_details:
        return None, None

    if len(action_details) == 1:
        change = next(iter(action_details.values()))
        if isinstance(change, dict) and "old" in change and "new" in change:
            return str(change["old"]), str(change["new"])

    return None, json.dumps(action_details)


def notify_change(
    *,
    project_uuid: str,
    user_email: str,
    date: pendulum.DateTime,
    action: str,
    object_id: Optional[str] = None,
    object_name: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    user_ip: Optional[str] = None,
) -> None:
    """
    Publish change history via weni-commons Notifier (Amazon MQ).

    object_name carries the concrete Nexus model/resource name.
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
            entity=Entity.USER,
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


def publish_recent_activity_to_amq(*, recent_activity: RecentActivities) -> None:
    old_value, new_value = _values_from_details(recent_activity.action_details)
    notify_change(
        project_uuid=str(recent_activity.project.uuid),
        user_email=recent_activity.created_by.email,
        date=pendulum.instance(recent_activity.created_at),
        action=recent_activity.action_type,
        object_id=str(recent_activity.uuid),
        object_name=recent_activity.action_model,
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
            object_name=dto.entity_name,
        )


def publish_brain_status_to_amq(*, user: str, project_uuid: str, brain_on: bool) -> None:
    notify_change(
        project_uuid=project_uuid,
        user_email=user,
        date=pendulum.now("UTC"),
        action="UPDATE",
        object_id=project_uuid,
        object_name="brain_on",
        old_value=str(not brain_on),
        new_value=str(brain_on),
    )
