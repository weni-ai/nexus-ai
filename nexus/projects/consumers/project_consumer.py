import logging

from sentry_sdk import capture_exception
from weni.eda.django.consumers import EDAConsumer as WeniEDAConsumer
from weni.eda.messages import Message as WeniMessage

from nexus.event_driven.parsers import JSONParser
from nexus.projects.models import Project
from nexus.projects.project_dto import ProjectCreationDTO
from nexus.usecases.projects.projects_use_case import ProjectsUseCase

logger = logging.getLogger(__name__)


def _build_project_dto(body: dict) -> ProjectCreationDTO:
    return ProjectCreationDTO(
        uuid=body.get("uuid"),
        name=body.get("name"),
        is_template=body.get("is_template"),
        template_type_uuid=body.get("template_type_uuid"),
        org_uuid=body.get("organization_uuid"),
        brain_on=body.get("brain_on"),
        authorizations=body.get("authorizations"),
        indexer_database=body.get("indexer_database") or Project.BEDROCK,
        inline_agent_switch=body.get("inline_agent_switch", True),
        is_live_desk_copilot=bool(body.get("is_live_desk_copilot", False)),
    )


class WeniEDAProjectConsumer(WeniEDAConsumer):
    """Consumer responsible for handling project creation events from Amazon MQ."""

    def consume(self, message: WeniMessage):
        body_len = len(message.body) if message.body else 0
        logger.info(
            "[WeniEDAProjectConsumer] Received project creation message body_len=%s",
            body_len,
        )
        try:
            body = JSONParser.parse(message.body)
            project_dto = _build_project_dto(body)
            logger.info(
                "[WeniEDAProjectConsumer] Processing project creation uuid=%s name=%s org=%s user=%s",
                project_dto.uuid,
                project_dto.name,
                project_dto.org_uuid,
                body.get("user_email"),
            )

            project_creation = ProjectsUseCase()
            project_creation.create_project(project_dto=project_dto, user_email=body.get("user_email"))

            self.ack()
            logger.info(
                "[WeniEDAProjectConsumer] Project created uuid=%s name=%s",
                project_dto.uuid,
                project_dto.name,
            )
        except Exception as exception:
            logger.error(
                "[WeniEDAProjectConsumer] Failed to create project: %s",
                exception,
                exc_info=True,
            )
            capture_exception(exception)
            raise
