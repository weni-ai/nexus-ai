import logging

import amqp
from sentry_sdk import capture_exception

from nexus.event_driven.consumer.consumers import EDAConsumer
from nexus.event_driven.parsers import JSONParser
from nexus.orgs.org_dto import OrgCreationDTO
from nexus.usecases.orgs.create import CreateOrgUseCase

logger = logging.getLogger(__name__)


class OrgConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        logger.debug(
            "[OrgConsumer] Consuming a message",
            extra={"body_len": len(message.body) if hasattr(message, "body") else None},
        )
        try:
            body = JSONParser.parse(message.body)

            org_dto = OrgCreationDTO(
                uuid=body.get("uuid"), name=body.get("name"), authorizations=body.get("authorizations")
            )

            org_creation = CreateOrgUseCase()
            org_creation.create_orgs(org_dto=org_dto, user_email=body.get("user_email"))

            message.channel.basic_ack(message.delivery_tag)
            logger.info("[OrgConsumer] Org created", extra={"uuid": org_dto.uuid})
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            logger.error("[OrgConsumer] Message rejected", exc_info=True)
