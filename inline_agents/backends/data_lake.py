import logging

from weni_datalake_sdk.clients.client import send_event_data
from weni_datalake_sdk.paths.events_path import EventPath
from nexus.celery import app as celery_app
import sentry_sdk

logger = logging.getLogger(__name__)

@celery_app.task
def send_data_lake_event(
    event_data: dict
):
    try:
        logger.info(f"Sending event data: {event_data}")
        response = send_event_data(EventPath, event_data)
        logger.info(f"Successfully sent data lake event: {response}")
        return response
    except Exception as e:
        logger.error(f"Failed to send data lake event: {str(e)}")
        sentry_sdk.set_tag("project_uuid", event_data.get("project", "unknown"))
        sentry_sdk.set_context("event_data", event_data)
        sentry_sdk.capture_exception(e)
        raise
