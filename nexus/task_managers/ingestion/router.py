import logging

from nexus.projects.models import Project
from nexus.task_managers.ingestion.constants import STRATEGY_JOB
from nexus.task_managers.ingestion.strategy import IngestionStrategyResolver
from nexus.task_managers.ingestion.telemetry import log_ingestion_route_decision

logger = logging.getLogger(__name__)


def route_file_ingestion(
    *,
    task_manager_uuid: str,
    project: Project,
    project_uuid: str,
    content_base_uuid: str,
    content_base_file_uuid: str,
    s3_uri: str,
) -> None:
    """Enqueue direct or job ingestion based on resolved project strategy."""
    from nexus.task_managers.tasks_bedrock import ingest_file_direct, start_ingestion_job

    effective_strategy = IngestionStrategyResolver.resolve(project)
    requested_strategy = IngestionStrategyResolver.requested_strategy(project)

    log_ingestion_route_decision(
        {
            "effective_strategy": effective_strategy,
            "requested_strategy": requested_strategy,
            "project_uuid": project_uuid,
            "content_base_uuid": content_base_uuid,
            "file_uuid": content_base_file_uuid,
            "task_manager_uuid": task_manager_uuid,
        }
    )

    if effective_strategy == STRATEGY_JOB:
        start_ingestion_job(task_manager_uuid, project_uuid=project_uuid)
        return

    ingest_file_direct.delay(
        task_manager_uuid=task_manager_uuid,
        project_uuid=project_uuid,
        content_base_uuid=content_base_uuid,
        content_base_file_uuid=content_base_file_uuid,
        s3_uri=s3_uri,
        strategy=effective_strategy,
    )
