import asyncio
import logging

from nexus.event_domain.decorators import observer
from nexus.event_domain.event_observer import EventObserver
from nexus.usecases.projects.project_type_update_eda import publish_project_type_update

logger = logging.getLogger(__name__)

PROJECT_TYPE_UPDATE_EDA_EVENT = "eda:project_type_update"


@observer(PROJECT_TYPE_UPDATE_EDA_EVENT, isolate_errors=True, manager="async")
class ProjectTypeUpdateEdaObserver(EventObserver):
    async def perform(self, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        user_email = kwargs.get("user_email") or ""
        is_multi_agents = kwargs.get("is_multi_agents")
        if not project_uuid or not isinstance(is_multi_agents, bool):
            logger.warning(
                "Skipping EDA project type update: missing project_uuid or invalid is_multi_agents "
                f"(project_uuid={project_uuid!r}, is_multi_agents={is_multi_agents!r})"
            )
            return

        try:
            await asyncio.to_thread(
                publish_project_type_update,
                project_uuid=project_uuid,
                user_email=user_email,
                is_multi_agents=is_multi_agents,
            )
        except Exception:
            logger.exception("Failed to publish project type update for project_uuid=%s", project_uuid)
