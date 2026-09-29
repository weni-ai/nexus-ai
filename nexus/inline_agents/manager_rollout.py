import logging
from typing import Any

from django.conf import settings
from weni.feature_flags.shortcuts import is_feature_active_for_attributes

from nexus.inline_agents.backends.openai.models import ManagerAgent
from nexus.projects.models import Project

logger = logging.getLogger(__name__)

MANAGER_2_8_FEATURE_FLAG = "enable_manager_2_8"


def _rollout_attributes(project_uuid: Any, user_email: str | None = None) -> dict[str, str]:
    attributes = {
        "weni_project": str(project_uuid),
        "projectUUID": str(project_uuid),
    }
    if user_email:
        attributes["userEmail"] = user_email
    return attributes


def can_select_manager_via_api(
    manager: ManagerAgent,
    project: Project,
    user_email: str | None = None,
) -> bool:
    """Block API assignment of private managers unless GrowthBook allows it.

    Admin FK assignment is unaffected. Re-saving the already linked manager
    stays allowed so a tester project does not 404 on an idempotent POST.
    """
    if manager.public:
        return True
    if project.manager_agent_id == manager.id:
        return True

    feature_flag = getattr(settings, "MANAGER_2_8_FEATURE_FLAG", MANAGER_2_8_FEATURE_FLAG)
    try:
        return is_feature_active_for_attributes(
            feature_flag,
            _rollout_attributes(project.uuid, user_email),
        )
    except Exception:
        logger.exception(
            "Failed to evaluate manager 2.8 rollout flag; denying API assignment",
            extra={"manager_uuid": str(manager.uuid), "project_uuid": str(project.uuid)},
        )
        return False
