import logging

import amqp
from weni.eda.parsers import JSONParser

from nexus.eda.consumers import NexusWeniConsumer
from nexus.projects.models import Project
from nexus.projects.project_dto import ProjectCreationDTO
from nexus.usecases.projects.projects_use_case import ProjectsUseCase

logger = logging.getLogger(__name__)


class ProjectConsumer(NexusWeniConsumer):
    consumer_log_prefix = "ProjectConsumer"

    def consume(self, message: amqp.Message):
        logger.debug(
            "[ProjectConsumer] Consuming a message",
            extra={"body_len": len(message.body) if hasattr(message, "body") else None},
        )
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
            inline_agent_switch=body.get("inline_agent_switch", True),
        )

        project_creation = ProjectsUseCase()
        project_creation.create_project(project_dto=project_dto, user_email=body.get("user_email"))

        self.ack()
        logger.info("[ProjectConsumer] Project created", extra={"uuid": project_dto.uuid})
