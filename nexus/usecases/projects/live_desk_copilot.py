import logging
from typing import Optional

from nexus.projects.models import Project

logger = logging.getLogger(__name__)

PARENT_UUID_KEYS = ("parent_uuid", "parent_project_uuid", "main_project_uuid")


def extract_parent_uuid(payload: dict) -> tuple[Optional[str], bool]:
    """Return (parent uuid or None, whether any known parent key was present)."""
    if not isinstance(payload, dict):
        return None, False
    for key in PARENT_UUID_KEYS:
        if key not in payload:
            continue
        value = payload.get(key)
        if value in (None, ""):
            return None, True
        return str(value), True
    return None, False


def assign_parent_project(project: Project, parent_uuid: Optional[str]) -> bool:
    """Set or clear `parent_project`. Returns True when the FK changed."""
    if not parent_uuid:
        if project.parent_project_id is None:
            return False
        project.parent_project = None
        return True

    if str(project.uuid) == str(parent_uuid):
        logger.warning(
            "[LiveDeskCopilot] Ignoring self-referential parent_project",
            extra={"project_uuid": str(project.uuid)},
        )
        return False

    try:
        parent = Project.objects.get(uuid=parent_uuid)
    except Project.DoesNotExist:
        logger.warning(
            "[LiveDeskCopilot] Parent project not found",
            extra={"project_uuid": str(project.uuid), "parent_uuid": parent_uuid},
        )
        return False

    if project.parent_project_id == parent.uuid:
        return False
    project.parent_project = parent
    return True


def vtex_runtime_fields(project: Project) -> dict[str, Optional[str]]:
    """VTEX fields agents should use: parent account for Live Desk copilots."""
    source = project
    if project.is_live_desk_copilot:
        parent = project.parent_project
        if parent is None and project.parent_project_id:
            parent = Project.objects.filter(pk=project.parent_project_id).first()
        if parent is not None:
            source = parent
    return {
        "vtex_account": source.vtex_account,
        "vtex_host_store": source.vtex_host_store,
        "storefront_type": source.storefront_type,
    }
