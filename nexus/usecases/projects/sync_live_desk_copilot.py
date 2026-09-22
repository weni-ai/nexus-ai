import logging
from typing import Literal, Optional

from django.db import transaction

from nexus.events import notify_async
from nexus.projects.models import Project
from nexus.usecases.projects.live_desk_copilot import assign_parent_project, extract_parent_uuid

logger = logging.getLogger(__name__)


class SyncLiveDeskCopilotUseCase:
    def sync(
        self,
        project_uuid: str,
        payload: dict,
        *,
        mode: Literal["create", "update"] = "update",
    ) -> Optional[Project]:
        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            logger.warning("[SyncLiveDeskCopilotUseCase] Project not found project_uuid=%s", project_uuid)
            return None

        update_fields: list[str] = []

        if mode == "create" or "is_live_desk_copilot" in payload:
            is_copilot = bool(payload.get("is_live_desk_copilot", False))
            if project.is_live_desk_copilot != is_copilot:
                project.is_live_desk_copilot = is_copilot
                update_fields.append("is_live_desk_copilot")

        parent_uuid, has_parent_key = extract_parent_uuid(payload)
        if has_parent_key:
            if assign_parent_project(project, parent_uuid):
                update_fields.append("parent_project")

        if not update_fields:
            return project

        with transaction.atomic():
            project.save(update_fields=update_fields)

        notify_async(event="cache_invalidation:project", project=project)
        logger.info(
            "[SyncLiveDeskCopilotUseCase] Live Desk copilot fields synced project_uuid=%s update_fields=%s mode=%s",
            project_uuid,
            update_fields,
            mode,
        )
        return project
