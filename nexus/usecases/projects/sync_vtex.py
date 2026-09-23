import logging
from dataclasses import dataclass
from typing import Literal, Optional

from django.db import IntegrityError, transaction
from sentry_sdk import capture_exception

from nexus.events import notify_async
from nexus.projects.models import Project

logger = logging.getLogger(__name__)

SYNCED_FIELD_PRESENCE = (
    ("vtex_account", "has_vtex_account"),
    ("vtex_host_store", "has_vtex_host_store"),
    ("storefront_type", "has_storefront_type"),
    ("timezone", "has_timezone"),
)


@dataclass(frozen=True)
class ProjectFields:
    vtex_account: Optional[str] = None
    vtex_host_store: Optional[str] = None
    storefront_type: Optional[str] = None
    timezone: Optional[str] = None
    has_vtex_account: bool = False
    has_vtex_host_store: bool = False
    has_storefront_type: bool = False
    has_timezone: bool = False


def unwrap_eda_payload(body: dict) -> dict:
    """Normalize AmazonMQ envelope (`event_type` + `data`) to a flat project payload.

    Only unwrap when both `event_type` and a dict `data` are present. A project
    payload may legitimately include a `data` field of its own; unwrapping on
    `data` alone would drop uuid, vtex_account and the rest of the root body.
    """
    if not isinstance(body, dict):
        return {}
    data = body.get("data")
    if "event_type" in body and isinstance(data, dict):
        return data
    return body


def extract_project_fields(payload: dict) -> ProjectFields:
    """Read synchronized fields from a Connect project create/update payload."""
    if not isinstance(payload, dict):
        return ProjectFields()

    config = payload.get("config")
    if not isinstance(config, dict):
        config = {}

    return ProjectFields(
        vtex_account=payload.get("vtex_account"),
        vtex_host_store=config.get("vtex_host_store"),
        storefront_type=config.get("storefront_type"),
        timezone=payload.get("timezone"),
        has_vtex_account="vtex_account" in payload,
        has_vtex_host_store="vtex_host_store" in config,
        has_storefront_type="storefront_type" in config,
        has_timezone="timezone" in payload,
    )


class SyncProjectFieldsUseCase:
    def sync_project_fields(
        self,
        project_uuid: str,
        fields: ProjectFields,
        *,
        mode: Literal["create", "update"] = "update",
    ) -> Optional[Project]:
        """Apply synchronized fields from a Connect project event.

        The two modes treat empty values differently on purpose. `update` applies
        the payload by key presence, so an explicit null clears the stored value.
        `create` only applies filled values because it also runs when a creation
        event is redelivered for an existing project; a stale creation payload
        must not wipe values already synced by a later update event.
        """
        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            logger.warning(
                "[SyncProjectFieldsUseCase] Project not found",
                extra={"project_uuid": project_uuid},
            )
            return None

        update_fields: list[str] = []
        for field_name, presence_name in SYNCED_FIELD_PRESENCE:
            value = getattr(fields, field_name)
            should_apply = bool(value) if mode == "create" else getattr(fields, presence_name)
            if should_apply:
                setattr(project, field_name, value)
                update_fields.append(field_name)

        if not update_fields:
            return project

        try:
            with transaction.atomic():
                project.save(update_fields=update_fields)
        except IntegrityError as exc:
            capture_exception(exc)
            logger.warning(
                "[SyncProjectFieldsUseCase] Unique constraint conflict on vtex_account",
                extra={
                    "project_uuid": project_uuid,
                    "vtex_account": fields.vtex_account,
                },
            )
            # The unique constraint blocked the write, so the persisted row is
            # unchanged. Skip cache invalidation and return a fresh instance
            # from the database instead of the in-memory object that still
            # holds the conflicting vtex_account.
            try:
                return Project.objects.get(uuid=project_uuid)
            except Project.DoesNotExist:
                return None

        notify_async(event="cache_invalidation:project", project=project)
        for copilot in Project.objects.filter(parent_project=project, is_live_desk_copilot=True):
            notify_async(event="cache_invalidation:project", project=copilot)
        logger.info(
            "[SyncProjectFieldsUseCase] Project fields synced",
            extra={"project_uuid": project_uuid, "update_fields": update_fields, "mode": mode},
        )
        return project
