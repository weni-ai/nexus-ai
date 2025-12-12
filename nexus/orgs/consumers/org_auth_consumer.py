import logging

import amqp
from sentry_sdk import capture_exception

from nexus.event_driven.consumer.consumers import EDAConsumer
from nexus.event_driven.parsers import JSONParser
from nexus.orgs.org_dto import OrgAuthCreationDTO
from nexus.usecases.orgs.create import CreateOrgAuthUseCase


class OrgAuthConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        logger.debug(
            "[OrgAuthConsumer] Consuming a message",
            extra={"body_len": len(message.body) if hasattr(message, "body") else None},
        )
        try:
            body = JSONParser.parse(message.body)
            org_auth_dto = OrgAuthCreationDTO(
                org_uuid=body.get("organization_uuid"), user_email=body.get("user_email"), role=body.get("role")
            )
            org_auth_creation = CreateOrgAuthUseCase()
            org_auth_creation.create_org_auth_with_dto(org_auth_dto=org_auth_dto)

            message.channel.basic_ack(message.delivery_tag)
            logger.info("[OrgAuthConsumer] Org Auth created", extra={"org_uuid": org_auth_dto.org_uuid})
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            logger.error("[OrgAuthConsumer] Message rejected", exc_info=True)


logger = logging.getLogger(__name__)
