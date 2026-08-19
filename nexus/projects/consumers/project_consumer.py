import json
import logging

from django.db import IntegrityError
from sentry_sdk import capture_exception
from weni.eda.django.consumers import EDAConsumer as WeniEDAConsumer
from weni.eda.messages import Message as WeniMessage

from nexus.event_driven.parsers import JSONParser
from nexus.projects.models import Project
from nexus.projects.project_dto import ProjectCreationDTO
from nexus.usecases.projects.projects_use_case import ProjectsUseCase

logger = logging.getLogger(__name__)


def _extract_project_payload(body: dict) -> dict:
    """Unwrap weni-engine event envelopes that nest the payload under ``data``."""
    if not isinstance(body, dict):
        return body

    nested = body.get("data")
    if isinstance(nested, dict) and body.get("event_type"):
        return nested

    return body


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
    )


class WeniEDAProjectConsumer(WeniEDAConsumer):
    """Consumer responsible for handling project creation events from Amazon MQ."""

    def consume(self, message: WeniMessage):
        raw_body = message.body.decode("utf-8") if message.body else ""
        logger.info(
            "[WeniEDAProjectConsumer] Received project creation message body=%s",
            raw_body,
        )
        try:
            parsed_body = JSONParser.parse(message.body)
            logger.info(
                "[WeniEDAProjectConsumer] Parsed project creation payload=%s",
                json.dumps(parsed_body, default=str),
            )
            body = _extract_project_payload(parsed_body)
            project_dto = _build_project_dto(body)
            logger.info(
                "[WeniEDAProjectConsumer] Processing project creation uuid=%s name=%s org=%s user=%s",
                project_dto.uuid,
                project_dto.name,
                project_dto.org_uuid,
                body.get("user_email"),
            )

            project_creation = ProjectsUseCase()
            try:
                project_creation.create_project(
                    project_dto=project_dto,
                    user_email=body.get("user_email"),
                )
            except IntegrityError:
                if Project.objects.filter(uuid=project_dto.uuid).exists():
                    logger.warning(
                        "[WeniEDAProjectConsumer] Project already exists uuid=%s, acknowledging duplicate message",
                        project_dto.uuid,
                    )
                    self.ack()
                    return
                raise

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
