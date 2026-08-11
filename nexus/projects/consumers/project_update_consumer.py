import logging

import amqp
from sentry_sdk import capture_exception

from nexus.event_driven.consumer.consumers import EDAConsumer
from nexus.event_driven.parsers import JSONParser
from nexus.usecases.projects.sync_vtex import (
    SyncProjectVtexUseCase,
    extract_vtex_fields,
    unwrap_eda_payload,
)

logger = logging.getLogger(__name__)

UPDATED_ACTION = "updated"


class ProjectUpdateConsumer(EDAConsumer):
    """Consumes Connect project update events (exchange update-projects.topic)."""

    def consume(self, message: amqp.Message):
        logger.debug(
            "[ProjectUpdateConsumer] Consuming a message",
            extra={"body_len": len(message.body) if hasattr(message, "body") else None},
        )
        try:
            body = unwrap_eda_payload(JSONParser.parse(message.body))
            action = body.get("action")

            if action != UPDATED_ACTION:
                message.channel.basic_ack(message.delivery_tag)
                logger.debug(
                    "[ProjectUpdateConsumer] Ignoring action",
                    extra={"action": action},
                )
                return

            project_uuid = body.get("project_uuid")
            if not project_uuid:
                message.channel.basic_ack(message.delivery_tag)
                logger.warning("[ProjectUpdateConsumer] Missing project_uuid, skipping")
                return

            vtex_fields = extract_vtex_fields(body)
            project = SyncProjectVtexUseCase().sync_project_vtex(
                str(project_uuid),
                vtex_fields,
                mode="update",
            )

            message.channel.basic_ack(message.delivery_tag)

            if project is None:
                logger.warning(
                    "[ProjectUpdateConsumer] Project not found, skipping VTEX sync",
                    extra={"project_uuid": project_uuid},
                )
            else:
                logger.info(
                    "[ProjectUpdateConsumer] Project VTEX fields updated",
                    extra={"project_uuid": project_uuid},
                )
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            logger.error("[ProjectUpdateConsumer] Message rejected", exc_info=True)
