import logging

import amqp
from django.db import IntegrityError, transaction
from sentry_sdk import capture_exception
from weni.eda.django.consumers import EDAConsumer as WeniEDAConsumer
from weni.eda.messages import Message as WeniMessage

from nexus.event_driven.consumer.consumers import EDAConsumer
from nexus.event_driven.parsers import JSONParser
from nexus.projects.models import Project
from nexus.projects.project_dto import ProjectCreationDTO
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from nexus.usecases.projects.sync_vtex import (
    SyncProjectVtexUseCase,
    extract_vtex_fields,
    unwrap_eda_payload,
)

logger = logging.getLogger(__name__)


def _extract_project_payload(body: dict) -> dict:
    return unwrap_eda_payload(body)


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


def _sync_created_project_vtex(project_uuid: str | None, vtex_fields) -> None:
    if not project_uuid:
        return
    SyncProjectVtexUseCase().sync_project_vtex(project_uuid, vtex_fields, mode="create")


def _handle_project_created(body: dict) -> str:
    payload = _extract_project_payload(body)
    project_uuid = payload.get("uuid")
    vtex_fields = extract_vtex_fields(payload)
    project_dto = _build_project_dto(payload)

    try:
        with transaction.atomic():
            ProjectsUseCase().create_project(project_dto=project_dto, user_email=payload.get("user_email"))
            _sync_created_project_vtex(project_uuid, vtex_fields)
        logger.info("[ProjectConsumer] Project created", extra={"uuid": project_uuid})
    except IntegrityError:
        if project_uuid and Project.objects.filter(uuid=project_uuid).exists():
            logger.info(
                "[ProjectConsumer] Project already exists, syncing VTEX fields only",
                extra={"uuid": project_uuid},
            )
            _sync_created_project_vtex(project_uuid, vtex_fields)
        else:
            raise

    return project_uuid


class OldProjectConsumer(EDAConsumer):
    # TODO: Remove this consumer once we permanently migrate to Weni EDA
    def consume(self, message: amqp.Message):
        logger.debug(
            "[OldProjectConsumer] Consuming a message",
            extra={"body_len": len(message.body) if hasattr(message, "body") else None},
        )
        try:
            body = JSONParser.parse(message.body)
            project_uuid = _handle_project_created(body)
            message.channel.basic_ack(message.delivery_tag)
            logger.info("[OldProjectConsumer] Project created", extra={"uuid": project_uuid})
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            logger.error("[OldProjectConsumer] Message rejected", exc_info=True)


class WeniEDAProjectConsumer(WeniEDAConsumer):
    """Consumer responsible for handling project creation events from Amazon MQ."""

    def consume(self, message: WeniMessage):
        logger.debug(
            "[WeniEDAProjectConsumer] Consuming a message",
            extra={"body_len": len(message.body) if message.body else None},
        )
        try:
            body = JSONParser.parse(message.body)
            project_uuid = _handle_project_created(body)
            self.ack()
            logger.info("[WeniEDAProjectConsumer] Project created", extra={"uuid": project_uuid})
        except Exception as exception:
            capture_exception(exception)
            raise
