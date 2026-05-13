import logging
from abc import ABC, abstractmethod
from typing import Optional

import pendulum
import sentry_sdk

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

    def _get_conversation(
        self,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: Optional[str] = None,
        conversation: Optional[object] = None,
    ) -> Optional[object]:
        """Return only a caller-supplied conversation object; do not load from Django ORM.

        AB 2.x inline traffic delegates conversation ownership to downstream consumers; the
        data lake path must not re-hydrate rows via implicit ORM queries.
        """
        return conversation if conversation else None

    def _get_conversation_uuid(
        self,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: Optional[str] = None,
        conversation: Optional[object] = None,
    ) -> Optional[str]:
        """Get conversation UUID from Conversation model or provided conversation object."""
        conversation_obj = self._get_conversation(
            project_uuid=project_uuid, contact_urn=contact_urn, channel_uuid=channel_uuid, conversation=conversation
        )
        if conversation_obj:
            return str(conversation_obj.uuid)
        return None

    def _enrich_metadata(
        self,
        event_data: dict,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: Optional[str] = None,
        agent_identifier: Optional[str] = None,
        conversation: Optional[object] = None,
        message_conversation_log_uuid: Optional[str] = None,
    ) -> None:
        """Enrich event metadata with agent_uuid, optional legacy conversation fields, and handoff id.

        AB 2.x inline: do not add ``conversation_uuid`` unless a legacy ORM ``conversation`` is passed.
        When ``message_conversation_log_uuid`` is provided, it is copied into metadata for analytics
        and correlation with conversation SQS (same id as ``message.sent`` message id where applicable).
        """
        event_data.setdefault("metadata", {})
        metadata = event_data["metadata"]

        # Get conversation object to extract all conversation fields
        conversation_obj = self._get_conversation(
            project_uuid=project_uuid, contact_urn=contact_urn, channel_uuid=channel_uuid, conversation=conversation
        )

        # Add conversation fields if conversation exists
        if conversation_obj:
            # Add conversation_uuid if missing
            if "conversation_uuid" not in metadata:
                metadata["conversation_uuid"] = str(conversation_obj.uuid)

            # Add conversation_start_date if missing and start_date exists
            if "conversation_start_date" not in metadata and conversation_obj.start_date:
                metadata["conversation_start_date"] = pendulum.instance(conversation_obj.start_date).to_iso8601_string()

            # Add conversation_end_date if missing and end_date exists
            if "conversation_end_date" not in metadata and conversation_obj.end_date:
                metadata["conversation_end_date"] = pendulum.instance(conversation_obj.end_date).to_iso8601_string()

        if message_conversation_log_uuid and "message_conversation_log_uuid" not in metadata:
            metadata["message_conversation_log_uuid"] = str(message_conversation_log_uuid)

        # Add agent_uuid if missing and agent_identifier is provided
        if "agent_uuid" not in metadata and agent_identifier:
            try:
                from nexus.inline_agents.models import IntegratedAgent

                team_agent = IntegratedAgent.objects.get(
                    agent__slug=agent_identifier, project__uuid=project_uuid, is_active=True
                )
                metadata["agent_uuid"] = str(team_agent.agent.uuid)
            except IntegratedAgent.DoesNotExist:
                logger.warning(
                    f"IntegratedAgent not found for agent_identifier={agent_identifier}, "
                    f"project_uuid={project_uuid}. Event will be sent without agent_uuid."
                )
                sentry_sdk.set_tag("project_uuid", project_uuid)
                sentry_sdk.set_context(
                    "agent_lookup", {"agent_identifier": agent_identifier, "project_uuid": project_uuid}
                )
                sentry_sdk.capture_message(f"IntegratedAgent not found: {agent_identifier}", level="warning")

    def _prepare_and_validate_event(
        self,
        event_data: dict,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: Optional[str] = None,
        agent_identifier: Optional[str] = None,
        conversation: Optional[object] = None,
        message_conversation_log_uuid: Optional[str] = None,
    ) -> dict:
        """Prepare event data, enrich metadata, and validate using DTO."""
        # Set required fields (will be validated by DTO)
        event_data.setdefault("project", project_uuid)
        event_data.setdefault("contact_urn", contact_urn)
        event_data.setdefault("date", pendulum.now("America/Sao_Paulo").to_iso8601_string())
        event_data.setdefault("event_name", "weni_nexus_data")

        # Enrich metadata with agent_uuid and optional correlation ids
        self._enrich_metadata(
            event_data=event_data,
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            agent_identifier=agent_identifier,
            conversation=conversation,
            message_conversation_log_uuid=message_conversation_log_uuid,
        )

        # Validate using DTO (will raise ValueError if validation fails)
        event_dto = DataLakeEventDTO(**event_data)
        event_dto.validate()
        return event_dto.dict()

    def process_custom_events(
        self,
        trace_data: dict,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: str,
        extractor: EventExtractor,
        preview: bool = False,
        conversation: Optional[object] = None,
        skip_conversation_sqs: bool = False,
        message_conversation_log_uuid: Optional[str] = None,
    ) -> None:
        """Process custom events using backend-specific extractor."""
        if preview:
            return None

        # Extract events using backend-specific extractor
        events = extractor.extract_events(trace_data)
        agent_identifier = extractor.get_agent_identifier(trace_data)

        for event_to_send in events:
            try:
                event_key = event_to_send.get("key")
                special_handlers = get_special_event_handlers()

                # Handle special events (CSAT, NPS, etc.) first
                if event_key in special_handlers:
                    special_handlers[event_key].process(
                        event_to_send,
                        project_uuid,
                        contact_urn,
                        channel_uuid,
                        conversation=conversation,
                        skip_conversation_sqs=skip_conversation_sqs,
                        sqs_correlation_id=message_conversation_log_uuid,
                    )

                self.send_custom_event(
                    event_data=event_to_send,
                    project_uuid=project_uuid,
                    contact_urn=contact_urn,
                    channel_uuid=channel_uuid,
                    agent_identifier=agent_identifier,
                    conversation=conversation,
                    message_conversation_log_uuid=message_conversation_log_uuid,
                )

            except Exception as e:
                logger.error(
                    f"Error processing custom event: {str(e)}. "
                    f"Event key: {event_to_send.get('key', 'unknown')}, "
                    f"Project: {project_uuid}"
                )
                sentry_sdk.set_tag("project_uuid", project_uuid)
                sentry_sdk.set_context(
                    "custom_event_error", {"event_data": event_to_send, "agent_identifier": agent_identifier}
                )
                sentry_sdk.capture_exception(e)

    def send_custom_event(
        self,
        event_data: dict,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: Optional[str] = None,
        agent_identifier: Optional[str] = None,
        conversation: Optional[object] = None,
        message_conversation_log_uuid: Optional[str] = None,
    ) -> Optional[dict]:
        """Send a custom event to data lake after validation."""
        try:
            # Extract agent_identifier from metadata if not provided
            if not agent_identifier:
                agent_identifier = event_data.get("metadata", {}).get("agent_name")

            validated_event = self._prepare_and_validate_event(
                event_data=event_data,
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                channel_uuid=channel_uuid,
                agent_identifier=agent_identifier,
                conversation=conversation,
                message_conversation_log_uuid=message_conversation_log_uuid,
            )

            self.send_data_lake_event_task.delay(validated_event)
            return validated_event
        except (ValueError, TypeError) as e:
            logger.error(
                f"Event validation failed: {str(e)}. "
                f"Event key: {event_data.get('key', 'unknown')}, "
                f"Project: {project_uuid}, Contact: {contact_urn}"
            )
            sentry_sdk.set_context(
                "custom event validation error",
                {
                    "event_data": event_data,
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "validation_error": str(e),
                },
            )
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.capture_exception(e)
            return None
        except Exception as e:
            logger.error(f"Error processing custom event for data lake: {str(e)}")
            sentry_sdk.set_context("custom event to data lake", {"event_data": event_data})
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.capture_exception(e)
            return None

    def send_validated_event(
        self,
        event_data: dict,
        project_uuid: str,
        contact_urn: str,
        use_delay: bool = True,
        channel_uuid: Optional[str] = None,
        agent_identifier: Optional[str] = None,
        conversation: Optional[object] = None,
        message_conversation_log_uuid: Optional[str] = None,
    ) -> Optional[dict]:
        """Send a validated event to data lake."""
        try:
            # Extract agent_identifier from event_data if not provided
            if not agent_identifier:
                metadata = event_data.get("metadata", {})
                if "agent_collaboration" in metadata:
                    agent_identifier = metadata["agent_collaboration"].get("agent_name")

            validated_event = self._prepare_and_validate_event(
                event_data=event_data,
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                channel_uuid=channel_uuid,
                agent_identifier=agent_identifier,
                conversation=conversation,
                message_conversation_log_uuid=message_conversation_log_uuid,
            )

            if use_delay:
                self.send_data_lake_event_task.delay(validated_event)
            else:
                self.send_data_lake_event_task(validated_event)

            return validated_event
        except (ValueError, TypeError) as e:
            logger.error(f"Event validation failed: {str(e)}")
            sentry_sdk.set_context("event validation error", {"event_data": event_data, "validation_error": str(e)})
            sentry_sdk.capture_exception(e)
            return None
