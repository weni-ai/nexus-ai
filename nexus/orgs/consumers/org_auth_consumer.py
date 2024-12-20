import amqp
from sentry_sdk import capture_exception

from nexus.orgs.org_dto import OrgAuthCreationDTO
from nexus.usecases.orgs.create import CreateOrgAuthUseCase
from nexus.usecases.users.create import CreateUserUseCase
from nexus.usecases.users.exceptions import UserDoesNotExists

from nexus.event_driven.parsers import JSONParser
from nexus.event_driven.consumer.consumers import EDAConsumer


class OrgAuthConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        def create():
            org_auth_creation = CreateOrgAuthUseCase()
            org_auth_creation.create_org_auth_with_dto(org_auth_dto=org_auth_dto)
            message.channel.basic_ack(message.delivery_tag)
            print(f"[OrgAuthConsumer] - Org Auth created: {org_auth_dto.org_uuid}")
        try:
            print(f"[OrgAuthConsumer] - Consuming a message. Body: {message.body}")
            body = JSONParser.parse(message.body)
            org_auth_dto = OrgAuthCreationDTO(
                org_uuid=body.get("organization_uuid"),
                user_email=body.get("user_email"),
                role=body.get("role")
            )
            create()
        except UserDoesNotExists:
            CreateUserUseCase().create_user(org_auth_dto.email)
            create(org_auth_dto)
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[OrgAuthConsumer] - Message rejected by: {exception}")
