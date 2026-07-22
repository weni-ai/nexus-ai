import logging
from typing import Any, Dict, Optional

from django.conf import settings
from weni.eda.django import AMQConnectionParamsFactory
from weni.eda.eda_publisher import EDAPublisher

from nexus.logs.models import RecentActivities

from .publishers_dto import RecentActivitiesDTO

logger = logging.getLogger(__name__)

ACTION_TYPE_TO_ACTION = {
    "C": "CREATE",
    "U": "UPDATE",
    "D": "DELETE",
}


def _payload_from_recent_activity(recent_activity: RecentActivities) -> Dict[str, Any]:
    # Provisional until Connect delivers the official contract.
    return {
        "uuid": str(recent_activity.uuid),
        "action": ACTION_TYPE_TO_ACTION.get(recent_activity.action_type, recent_activity.action_type),
        "action_type": recent_activity.action_type,
        "entity": "NEXUS",
        "action_model": recent_activity.action_model,
        "action_details": recent_activity.action_details or {},
        "project_uuid": str(recent_activity.project.uuid),
        "user": recent_activity.created_by.email,
        "intelligence_uuid": (str(recent_activity.intelligence.uuid) if recent_activity.intelligence_id else None),
        "created_at": recent_activity.created_at.isoformat() if recent_activity.created_at else None,
    }


def _payload_from_external_dto(dto: RecentActivitiesDTO) -> Dict[str, Any]:
    return {
        "action": dto.action,
        "entity": dto.entity,
        "user": dto.user.email,
        "organization_uuid": str(dto.org.uuid),
        "entity_name": dto.entity_name,
    }


def publish_recent_activity_to_amq(
    *,
    recent_activity: Optional[RecentActivities] = None,
    body: Optional[Dict[str, Any]] = None,
) -> None:
    """Additive Amazon MQ publish. Does not replace DB save or legacy RabbitMQ."""
    if body is None and recent_activity is not None:
        body = _payload_from_recent_activity(recent_activity)
    if not body:
        return

    exchange = getattr(settings, "RECENT_ACTIVITIES_AMQ_EXCHANGE", "recent-activities.topic")
    routing_key = getattr(settings, "RECENT_ACTIVITIES_AMQ_ROUTING_KEY", "")

    try:
        EDAPublisher(AMQConnectionParamsFactory).send_message(
            body=body,
            exchange=exchange,
            routing_key=routing_key,
        )
    except Exception:
        logger.exception("Failed to publish recent activity to Amazon MQ")


def publish_external_recent_activity_to_amq(dto: RecentActivitiesDTO) -> None:
    publish_recent_activity_to_amq(body=_payload_from_external_dto(dto))


def publish_brain_status_to_amq(*, user: str, project_uuid: str, brain_on: bool) -> None:
    publish_recent_activity_to_amq(
        body={
            "action": "UPDATE",
            "entity": "NEXUS",
            "user": user,
            "project_uuid": project_uuid,
            "brain_on": brain_on,
            "action_model": "Project",
            "routing_hint": "brain_status",
        }
    )
