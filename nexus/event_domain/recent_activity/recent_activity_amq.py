import logging
from typing import Any, Dict, Optional
from uuid import uuid4

import pendulum
from django.conf import settings
from weni.eda.django import AMQConnectionParamsFactory
from weni.eda.eda_publisher import EDAPublisher

from nexus.logs.models import RecentActivities

from .publishers_dto import RecentActivitiesDTO

logger = logging.getLogger(__name__)

PRODUCER = "nexus-ai"
DEFAULT_MODULE = "nexus"

ACTION_TYPE_TO_ACTION = {
    "C": "CREATE",
    "U": "UPDATE",
    "D": "DELETE",
}

ACTION_TO_EVENT_SUFFIX = {
    "CREATE": "created",
    "UPDATE": "updated",
    "DELETE": "deleted",
    "C": "created",
    "U": "updated",
    "D": "deleted",
}


def _to_utc_z(value) -> str:
    return pendulum.instance(value).in_timezone("UTC").to_iso8601_string()


def _event_type(*, entity: str, action: str) -> str:
    suffix = ACTION_TO_EVENT_SUFFIX.get(action, action.lower())
    return f"nexus.{entity.lower()}.{suffix}"


def notify_change(
    *,
    project_uuid: str,
    user_email: str,
    date: pendulum.DateTime,
    action: str,
    entity: str,
    module: str = DEFAULT_MODULE,
    object_id: Optional[str] = None,
    object_name: Optional[str] = None,
    user_ip: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> None:
    """
    Publish a change-history event to Amazon MQ.

    Mirrors the weni-commons Notifier.notify_change contract Sandro is introducing.
    Envelope format agreed for Change History:
    event_id, event_type, producer, timestamp, correlation_id, data.
    """
    if not project_uuid:
        logger.warning("Skipping change-history AMQ publish: missing project_uuid")
        return

    event_id = str(uuid4())
    timestamp = _to_utc_z(date)
    body: Dict[str, Any] = {
        "event_id": event_id,
        "event_type": _event_type(entity=entity, action=action),
        "producer": PRODUCER,
        "timestamp": timestamp,
        "correlation_id": correlation_id,
        "data": {
            "project_uuid": project_uuid,
            "user_email": user_email,
            "date": timestamp,
            "action": action,
            "entity": entity,
            "module": module,
            "object_id": object_id,
            "object_name": object_name,
            "user_ip": user_ip,
        },
    }

    exchange = getattr(settings, "RECENT_ACTIVITIES_AMQ_EXCHANGE", "change-history.topic")
    routing_key = getattr(settings, "RECENT_ACTIVITIES_AMQ_ROUTING_KEY", "")

    try:
        EDAPublisher(AMQConnectionParamsFactory).send_message(
            body=body,
            exchange=exchange,
            routing_key=routing_key,
        )
    except Exception:
        logger.exception("Failed to publish change history to Amazon MQ")


def publish_recent_activity_to_amq(*, recent_activity: RecentActivities) -> None:
    """Map a persisted RecentActivities row into notify_change."""
    action = ACTION_TYPE_TO_ACTION.get(recent_activity.action_type, recent_activity.action_type)
    notify_change(
        project_uuid=str(recent_activity.project.uuid),
        user_email=recent_activity.created_by.email,
        date=pendulum.instance(recent_activity.created_at),
        action=action,
        entity=recent_activity.action_model,
        object_id=str(recent_activity.uuid),
        object_name=recent_activity.action_model,
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
            entity=dto.entity,
            object_name=dto.entity_name,
        )


def publish_brain_status_to_amq(*, user: str, project_uuid: str, brain_on: bool) -> None:
    notify_change(
        project_uuid=project_uuid,
        user_email=user,
        date=pendulum.now("UTC"),
        action="UPDATE",
        entity="Project",
        object_id=project_uuid,
        object_name=f"brain_on={brain_on}",
    )
