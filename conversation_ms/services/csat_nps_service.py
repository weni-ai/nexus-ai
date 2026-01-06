import logging

import pendulum
import sentry_sdk
from django.conf import settings

from inline_agents.backends.data_lake import send_data_lake_event
from inline_agents.data_lake.event_dto import DataLakeEventDTO

logger = logging.getLogger(__name__)


class CSATNPSService:
    def process_csat_event(self, event_data: dict, conversation, project_uuid: str, contact_urn: str):
        try:
            csat_value = event_data.get("value")
            if not csat_value:
                logger.warning("[CSATNPSService] CSAT event missing value", extra={"event_data": event_data})
                return

            if conversation and conversation.channel_uuid:
                from nexus.usecases.inline_agents.update import update_conversation_data

                update_conversation_data(
                    to_update={"csat": csat_value},
                    project_uuid=project_uuid,
                    contact_urn=contact_urn,
                    channel_uuid=str(conversation.channel_uuid),
                )
                conversation.refresh_from_db()

            event_dto = DataLakeEventDTO(
                event_name="weni_nexus_data",
                date=pendulum.now("America/Sao_Paulo").to_iso8601_string(),
                project=project_uuid,
                contact_urn=contact_urn,
                key="weni_csat",
                value_type="string",
                value=str(csat_value),
                metadata={
                    "agent_uuid": settings.AGENT_UUID_CSAT,
                    "conversation_uuid": str(conversation.uuid) if conversation else None,
                },
            )

            if conversation:
                if conversation.start_date:
                    event_dto.metadata["conversation_start_date"] = pendulum.instance(
                        conversation.start_date
                    ).to_iso8601_string()
                if conversation.end_date:
                    event_dto.metadata["conversation_end_date"] = pendulum.instance(
                        conversation.end_date
                    ).to_iso8601_string()

            validated_event = event_dto.dict()
            send_data_lake_event.delay(validated_event)

            logger.info(
                "[CSATNPSService] CSAT event sent to datalake",
                extra={
                    "conversation_uuid": str(conversation.uuid) if conversation else None,
                    "csat_value": csat_value,
                },
            )

        except Exception as e:
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.set_tag("contact_urn", contact_urn)
            sentry_sdk.set_context(
                "csat_nps_service",
                {
                    "event_type": "csat",
                    "event_data": event_data,
                    "conversation_uuid": str(conversation.uuid) if conversation else None,
                },
            )
            sentry_sdk.capture_exception(e)
            logger.error(
                "[CSATNPSService] Error processing CSAT event",
                extra={"event_data": event_data, "error": str(e)},
                exc_info=True,
            )
            raise

    def process_nps_event(self, event_data: dict, conversation, project_uuid: str, contact_urn: str):
        try:
            nps_value = event_data.get("value")
            if not nps_value:
                logger.warning("[CSATNPSService] NPS event missing value", extra={"event_data": event_data})
                return

            if conversation and conversation.channel_uuid:
                from nexus.usecases.inline_agents.update import update_conversation_data

                update_conversation_data(
                    to_update={"nps": nps_value},
                    project_uuid=project_uuid,
                    contact_urn=contact_urn,
                    channel_uuid=str(conversation.channel_uuid),
                )
                conversation.refresh_from_db()

            event_dto = DataLakeEventDTO(
                event_name="weni_nexus_data",
                date=pendulum.now("America/Sao_Paulo").to_iso8601_string(),
                project=project_uuid,
                contact_urn=contact_urn,
                key="weni_nps",
                value_type="string",
                value=str(nps_value),
                metadata={
                    "agent_uuid": settings.AGENT_UUID_NPS,
                    "conversation_uuid": str(conversation.uuid) if conversation else None,
                },
            )

            if conversation:
                if conversation.start_date:
                    event_dto.metadata["conversation_start_date"] = pendulum.instance(
                        conversation.start_date
                    ).to_iso8601_string()
                if conversation.end_date:
                    event_dto.metadata["conversation_end_date"] = pendulum.instance(
                        conversation.end_date
                    ).to_iso8601_string()

            validated_event = event_dto.dict()
            send_data_lake_event.delay(validated_event)

            logger.info(
                "[CSATNPSService] NPS event sent to datalake",
                extra={
                    "conversation_uuid": str(conversation.uuid) if conversation else None,
                    "nps_value": nps_value,
                },
            )

        except Exception as e:
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.set_tag("contact_urn", contact_urn)
            sentry_sdk.set_context(
                "csat_nps_service",
                {
                    "event_type": "nps",
                    "event_data": event_data,
                    "conversation_uuid": str(conversation.uuid) if conversation else None,
                },
            )
            sentry_sdk.capture_exception(e)
            logger.error(
                "[CSATNPSService] Error processing NPS event",
                extra={"event_data": event_data, "error": str(e)},
                exc_info=True,
            )
            raise
