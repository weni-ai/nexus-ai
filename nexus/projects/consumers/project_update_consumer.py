import logging

import amqp
from sentry_sdk import capture_exception
from weni.eda.django.consumers import EDAConsumer as WeniEDAConsumer
from weni.eda.messages import Message as WeniMessage

from nexus.event_driven.consumer.consumers import EDAConsumer
from nexus.event_driven.parsers import JSONParser
from nexus.usecases.projects.sync_vtex import (
    SyncProjectVtexUseCase,
    extract_vtex_fields,
    unwrap_eda_payload,
)

logger = logging.getLogger(__name__)

UPDATED_ACTION = "updated"


def _handle_project_updated(body: dict) -> tuple[str | None, bool]:
    """
    Apply VTEX snapshot from a Connect project update event.

    Returns (project_uuid, skipped) where skipped is True when the action
    is ignored or project_uuid is missing.
    """
    payload = unwrap_eda_payload(body)
    action = payload.get("action")

    if action != UPDATED_ACTION:
        logger.debug("[ProjectUpdateConsumer] Ignoring action", extra={"action": action})
        return None, True

    project_uuid = payload.get("project_uuid")
    if not project_uuid:
        logger.warning("[ProjectUpdateConsumer] Missing project_uuid, skipping")
        return None, True

    vtex_fields = extract_vtex_fields(payload)
    project = SyncProjectVtexUseCase().sync_project_vtex(
        str(project_uuid),
        vtex_fields,
        mode="update",
    )

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

    return str(project_uuid), False


class ProjectUpdateConsumer(EDAConsumer):
    """Consumes Connect project update events on the legacy RabbitMQ broker."""

    def consume(self, message: amqp.Message):
        logger.debug(
            "[ProjectUpdateConsumer] Consuming a message",
            extra={"body_len": len(message.body) if hasattr(message, "body") else None},
        )
        try:
            body = JSONParser.parse(message.body)
            _handle_project_updated(body)
            message.channel.basic_ack(message.delivery_tag)
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            logger.error("[ProjectUpdateConsumer] Message rejected", exc_info=True)


class WeniEDAProjectUpdateConsumer(WeniEDAConsumer):
    """Consumes Connect project update events from Amazon MQ.

    Not registered in `handle_amq_consumers` yet: Connect still publishes project
    updates only to the legacy RabbitMQ broker.
    """

    def consume(self, message: WeniMessage):
        logger.debug(
            "[WeniEDAProjectUpdateConsumer] Consuming a message",
            extra={"body_len": len(message.body) if message.body else None},
        )
        try:
            body = JSONParser.parse(message.body)
            _handle_project_updated(body)
            self.ack()
        except Exception as exception:
            capture_exception(exception)
            raise
