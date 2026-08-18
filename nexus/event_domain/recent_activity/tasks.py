import logging

import pendulum
from django.apps import apps

from nexus.celery import app

logger = logging.getLogger(__name__)


@app.task(
    name="nexus.event_domain.recent_activity.tasks.notify_change_task",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def notify_change_task(self, **payload):
    """Publish a single change-history event on Amazon MQ from a Celery worker."""
    from nexus.event_domain.recent_activity.recent_activity_amq import notify_change

    date_iso = payload.pop("date_iso")
    try:
        notify_change(date=pendulum.parse(date_iso), **payload)
    except Exception as exc:
        logger.exception("Failed to publish change history task")
        raise self.retry(exc=exc) from exc


@app.task(
    name="nexus.event_domain.recent_activity.tasks.publish_recent_activity_task",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def publish_recent_activity_task(self, recent_activity_uuid: str, object_name: str, object_id: str):
    """Publish change history for a persisted RecentActivities row."""
    from nexus.event_domain.recent_activity.recent_activity_amq import (
        publish_recent_activity_to_amq_sync,
    )
    from nexus.logs.models import RecentActivities

    try:
        recent_activity = RecentActivities.objects.select_related("project", "created_by").get(
            uuid=recent_activity_uuid
        )
        publish_recent_activity_to_amq_sync(
            recent_activity=recent_activity,
            object_name=object_name,
            object_id=object_id,
        )
    except Exception as exc:
        logger.exception(
            "Failed to publish recent activity task recent_activity_uuid=%s",
            recent_activity_uuid,
        )
        raise self.retry(exc=exc) from exc


@app.task(
    name="nexus.event_domain.recent_activity.tasks.publish_external_recent_activity_task",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def publish_external_recent_activity_task(
    self,
    org_uuid: str,
    user_email: str,
    entity_name: str,
    action: str,
    action_model: str,
):
    """Fan out org-level recent activity events from a Celery worker."""
    from nexus.event_domain.recent_activity.publishers_dto import RecentActivitiesDTO
    from nexus.event_domain.recent_activity.recent_activity_amq import (
        publish_external_recent_activity_to_amq_sync,
    )

    Org = apps.get_model("orgs", "Org")
    User = apps.get_model("users", "User")

    try:
        org = Org.objects.get(uuid=org_uuid)
        user = User.objects.get(email=user_email)
        dto = RecentActivitiesDTO(
            org=org,
            user=user,
            entity_name=entity_name,
            action=action,
            action_model=action_model,
        )
        publish_external_recent_activity_to_amq_sync(dto)
    except Exception as exc:
        logger.exception(
            "Failed to publish external recent activity task org_uuid=%s action=%s",
            org_uuid,
            action,
        )
        raise self.retry(exc=exc) from exc
