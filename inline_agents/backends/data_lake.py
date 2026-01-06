import logging

import sentry_sdk
from weni_datalake_sdk.clients.client import send_event_data
from weni_datalake_sdk.paths.events_path import EventPath

from nexus.celery import app as celery_app

logger = logging.getLogger(__name__)


@celery_app.task
def send_data_lake_event(payload: dict):
    """
    Process and send event to data lake.
    
    If payload contains 'event_data' directly (compatibility with old code),
    send directly. Otherwise, process full payload making DB queries in the worker.
    
    Args:
        payload: Dict with 'event_data' (old mode) or full payload with:
            - event_data: dict with event data (no enrichment)
            - project_uuid: str
            - contact_urn: str
            - channel_uuid: Optional[str]
            - agent_identifier: Optional[str]
            - conversation_uuid: Optional[str]
            - backend: str
            - foundation_model: str
    """
    try:
        # Compatibility: detect if it's old mode (validated event_data) or new mode (full payload) Deprecated will be removed soon
        is_old_format = "event_data" not in payload and all(key in payload for key in ["project", "contact_urn", "key"])
        
        if is_old_format:
            event_data = payload
            logger.info(f"Sending event data (old format): {event_data.get('key', 'unknown')}")
            response = send_event_data(EventPath, event_data)
            logger.info(f"Successfully sent data lake event: {response}")
            return response

        from inline_agents.data_lake.event_service import DataLakeEventService

        service = DataLakeEventService(send_data_lake_event_task=send_data_lake_event)

        validated_event = service._prepare_and_validate_event(
            event_data=payload["event_data"],
            project_uuid=payload["project_uuid"],
            contact_urn=payload["contact_urn"],
            channel_uuid=payload.get("channel_uuid"),
            agent_identifier=payload.get("agent_identifier"),
            conversation=None,
        )
        
        logger.info(f"Sending event data: {validated_event.get('key', 'unknown')}")
        response = send_event_data(EventPath, validated_event)
        logger.info(f"Successfully sent data lake event: {response}")
        return response

    except Exception as e:
        project_uuid = payload.get("project_uuid") or payload.get("project", "unknown")
        logger.error(f"Failed to send data lake event: {str(e)}")
        sentry_sdk.set_tag("project_uuid", project_uuid)
        sentry_sdk.set_context("event_data", payload)
        sentry_sdk.capture_exception(e)
        raise
