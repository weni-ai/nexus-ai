import logging

import amqp
from sentry_sdk import capture_exception

from nexus.event_driven.consumer.consumers import EDAConsumer
from nexus.event_driven.parsers import JSONParser
from nexus.projects.models import Project
from nexus.projects.project_dto import ProjectCreationDTO
from nexus.usecases.projects.projects_use_case import ProjectsUseCase

logger = logging.getLogger(__name__)


class ProjectConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        logger.debug(
            "[ProjectConsumer] Consuming a message",
            extra={"body_len": len(message.body) if hasattr(message, "body") else None},
        )
        try:
            body = JSONParser.parse(message.body)

            project_dto = ProjectCreationDTO(
                uuid=body.get("uuid"),
                name=body.get("name"),
                is_template=body.get("is_template"),
                template_type_uuid=body.get("template_type_uuid"),
                org_uuid=body.get("organization_uuid"),
                brain_on=body.get("brain_on"),
                authorizations=body.get("authorizations"),
                indexer_database=body.get("indexer_database") or Project.BEDROCK,
            )

            project_creation = ProjectsUseCase()
            project_creation.create_project(project_dto=project_dto, user_email=body.get("user_email"))

            message.channel.basic_ack(message.delivery_tag)
            logger.info("[ProjectConsumer] Project created", extra={"uuid": project_dto.uuid})
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            logger.error("[ProjectConsumer] Message rejected", exc_info=True)
