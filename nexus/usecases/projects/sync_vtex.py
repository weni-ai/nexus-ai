import logging
from dataclasses import dataclass
from typing import Literal, Optional

from django.db import IntegrityError, transaction
from sentry_sdk import capture_exception

from nexus.projects.models import Project

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VtexFields:
    vtex_account: Optional[str] = None
    vtex_host_store: Optional[str] = None
    storefront_type: Optional[str] = None
    has_vtex_account: bool = False
    has_vtex_host_store: bool = False
    has_storefront_type: bool = False


def unwrap_eda_payload(body: dict) -> dict:
    """Normalize AmazonMQ envelope (`event_type` + `data`) to a flat project payload."""
    if not isinstance(body, dict):
        return {}
    data = body.get("data")
    if isinstance(data, dict):
        return data
    return body


def extract_vtex_fields(payload: dict) -> VtexFields:
    """Read VTEX fields from a Connect project create/update payload."""
    if not isinstance(payload, dict):
        return VtexFields()

    config = payload.get("config")
    if not isinstance(config, dict):
        config = {}

    return VtexFields(
        vtex_account=payload.get("vtex_account"),
        vtex_host_store=config.get("vtex_host_store"),
        storefront_type=config.get("storefront_type"),
        has_vtex_account="vtex_account" in payload,
        has_vtex_host_store="vtex_host_store" in config,
        has_storefront_type="storefront_type" in config,
    )


class SyncProjectVtexUseCase:
    def sync_project_vtex(
        self,
        project_uuid: str,
        fields: VtexFields,
        *,
        mode: Literal["create", "update"] = "update",
    ) -> Optional[Project]:
        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            logger.warning(
                "[SyncProjectVtexUseCase] Project not found",
                extra={"project_uuid": project_uuid},
            )
            return None

        update_fields: list[str] = []

        if mode == "create":
            if fields.vtex_account:
                project.vtex_account = fields.vtex_account
                update_fields.append("vtex_account")
            if fields.vtex_host_store:
                project.vtex_host_store = fields.vtex_host_store
                update_fields.append("vtex_host_store")
            if fields.storefront_type:
                project.storefront_type = fields.storefront_type
                update_fields.append("storefront_type")
        else:
            if fields.has_vtex_account:
                project.vtex_account = fields.vtex_account
                update_fields.append("vtex_account")
            if fields.has_vtex_host_store:
                project.vtex_host_store = fields.vtex_host_store
                update_fields.append("vtex_host_store")
            if fields.has_storefront_type:
                project.storefront_type = fields.storefront_type
                update_fields.append("storefront_type")

        if not update_fields:
            return project

        try:
            with transaction.atomic():
                project.save(update_fields=update_fields)
        except IntegrityError as exc:
            capture_exception(exc)
            logger.warning(
                "[SyncProjectVtexUseCase] Unique constraint conflict on vtex_account",
                extra={
                    "project_uuid": project_uuid,
                    "vtex_account": fields.vtex_account,
                },
            )
            project.refresh_from_db()
            return project

        logger.info(
            "[SyncProjectVtexUseCase] Project VTEX fields synced",
            extra={"project_uuid": project_uuid, "update_fields": update_fields, "mode": mode},
        )
        return project
