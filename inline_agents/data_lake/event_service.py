import logging
import pendulum
import sentry_sdk

from abc import ABC, abstractmethod
from typing import Optional

from inline_agents.data_lake.event_dto import DataLakeEventDTO
from inline_agents.data_lake.special_event_handler import get_special_event_handlers

logger = logging.getLogger(__name__)


class EventExtractor(ABC):
    """Abstract base class for extracting events from backend-specific trace formats."""

    @abstractmethod
    def extract_events(self, trace_data: dict) -> list[dict]:
        """Extract events from backend-specific trace format."""
        pass

    @abstractmethod
    def get_agent_identifier(self, trace_data: dict) -> str:
        """Get agent identifier (name/slug) from trace data."""
        pass


class DataLakeEventService:
    """Base service for processing and sending events to data lake."""

    def __init__(self, send_data_lake_event_task: callable):
        self.send_data_lake_event_task = send_data_lake_event_task

    def process_custom_events(
        self,
        trace_data: dict,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: str,
        extractor: EventExtractor,
        preview: bool = False
    ) -> None:
        """Process custom events using backend-specific extractor."""
        from nexus.inline_agents.models import IntegratedAgent

        if preview:
            return None

        # Extract events using backend-specific extractor
        events = extractor.extract_events(trace_data)
        agent_identifier = extractor.get_agent_identifier(trace_data)

        for event_to_send in events:
            try:
                # Ensure metadata exists
                if "metadata" not in event_to_send or event_to_send.get("metadata") is None:
                    event_to_send["metadata"] = {}

                event_key = event_to_send.get("key")
                special_handlers = get_special_event_handlers()

                # Handle special events (CSAT, NPS, etc.) first
                if event_key in special_handlers:
                    special_handlers[event_key].process(
                        event_to_send,
                        project_uuid,
                        contact_urn,
                        channel_uuid
                    )
                # For regular events, add agent_uuid if missing and agent_identifier is provided
                elif "agent_uuid" not in event_to_send.get("metadata", {}) and agent_identifier:
                    try:
                        team_agent = IntegratedAgent.objects.get(
                            agent__slug=agent_identifier,
                            project__uuid=project_uuid
                        )
                        agent_uuid = team_agent.agent.uuid
                        event_to_send["metadata"]["agent_uuid"] = agent_uuid
                    except IntegratedAgent.DoesNotExist:
                        logger.warning(
                            f"IntegratedAgent not found for agent_identifier={agent_identifier}, "
                            f"project_uuid={project_uuid}. Event will be sent without agent_uuid."
                        )
                        sentry_sdk.set_tag("project_uuid", project_uuid)
                        sentry_sdk.set_context("custom_event", {
                            "agent_identifier": agent_identifier,
                            "event_key": event_to_send.get("key")
                        })
                        sentry_sdk.capture_message(
                            f"IntegratedAgent not found for custom event: {agent_identifier}",
                            level="warning"
                        )

                self._send_custom_event(
                    event_data=event_to_send,
                    project_uuid=project_uuid,
                    contact_urn=contact_urn
                )
            except Exception as e:
                logger.error(
                    f"Error processing custom event: {str(e)}. "
                    f"Event key: {event_to_send.get('key', 'unknown')}, "
                    f"Project: {project_uuid}"
                )
                sentry_sdk.set_tag("project_uuid", project_uuid)
                sentry_sdk.set_context("custom_event_error", {
                    "event_data": event_to_send,
                    "agent_identifier": agent_identifier
                })
                sentry_sdk.capture_exception(e)
                # Continue processing other events even if one fails

    def _send_custom_event(
        self,
        event_data: dict,
        project_uuid: str,
        contact_urn: str
    ) -> Optional[dict]:
        """Send a custom event to data lake after validation."""
        try:
            # Ensure required fields are set
            event_data["project"] = project_uuid
            event_data["contact_urn"] = contact_urn

            # Set date if not present
            if "date" not in event_data or not event_data.get("date"):
                event_data["date"] = pendulum.now("America/Sao_Paulo").to_iso8601_string()

            # Ensure event_name is set
            if "event_name" not in event_data:
                event_data["event_name"] = "weni_nexus_data"

            # Validate event using DTO
            try:
                event_dto = DataLakeEventDTO(**event_data)
                event_dto.validate()
                validated_event = event_dto.dict()
            except (ValueError, TypeError) as e:
                logger.error(
                    f"Event validation failed: {str(e)}. "
                    f"Event key: {event_data.get('key', 'unknown')}, "
                    f"Project: {project_uuid}, Contact: {contact_urn}"
                )
                sentry_sdk.set_context("custom event validation error", {
                    "event_data": event_data,
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "validation_error": str(e)
                })
                sentry_sdk.set_tag("project_uuid", project_uuid)
                sentry_sdk.capture_message(
                    f"Event validation failed: {str(e)}",
                    level="error"
                )
                return None

            # Send validated event to data lake
            self.send_data_lake_event_task.delay(validated_event)
            return validated_event
        except Exception as e:
            logger.error(f"Error processing custom event for data lake: {str(e)}")
            sentry_sdk.set_context("custom event to data lake", {"event_data": event_data})
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.capture_exception(e)
            return None

    def send_validated_event(
        self,
        event_data: dict,
        use_delay: bool = True
    ) -> Optional[dict]:
        """Send a validated event to data lake."""
        try:
            event_dto = DataLakeEventDTO(**event_data)
            event_dto.validate()
            validated_event = event_dto.dict()

            if use_delay:
                self.send_data_lake_event_task.delay(validated_event)
            else:
                self.send_data_lake_event_task(validated_event)

            return validated_event
        except (ValueError, TypeError) as e:
            logger.error(f"Event validation failed: {str(e)}")
            sentry_sdk.set_context("event validation error", {
                "event_data": event_data,
                "validation_error": str(e)
            })
            sentry_sdk.capture_exception(e)
            return None
