import amqp
from sentry_sdk import capture_exception

from nexus.event_driven.consumer.consumers import EDAConsumer
from nexus.event_driven.parsers import JSONParser
from nexus.orgs.org_dto import OrgCreationDTO
from nexus.usecases.orgs.create import CreateOrgUseCase


class OrgConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        print(f"[OrgConsumer] - Consuming a message. Body: {message.body}")
        try:
            body = JSONParser.parse(message.body)

            org_dto = OrgCreationDTO(
                uuid=body.get("uuid"), name=body.get("name"), authorizations=body.get("authorizations")
            )

            org_creation = CreateOrgUseCase()
            org_creation.create_orgs(org_dto=org_dto, user_email=body.get("user_email"))

            message.channel.basic_ack(message.delivery_tag)
            print(f"[OrgConsumer] - Org created: {org_dto.uuid}")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[OrgConsumer] - Message rejected by: {exception}")
