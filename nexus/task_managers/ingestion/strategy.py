from django.conf import settings

from nexus.projects.models import Project
from nexus.task_managers.ingestion.constants import STRATEGY_JOB

_EXPERIMENT_ENVIRONMENTS = frozenset({"staging", "development"})


class IngestionStrategyResolver:
    @staticmethod
    def is_experiment_eligible(project: Project) -> bool:
        environment = getattr(settings, "ENVIRONMENT", "").lower()
        if environment in _EXPERIMENT_ENVIRONMENTS:
            return True
        allowlist = getattr(settings, "BEDROCK_DIRECT_INGESTION_PROJECT_ALLOWLIST", [])
        return str(project.uuid) in allowlist

    @classmethod
    def resolve(cls, project: Project) -> str:
        requested = getattr(project, "bedrock_ingestion_strategy", STRATEGY_JOB) or STRATEGY_JOB
        if requested == STRATEGY_JOB:
            return STRATEGY_JOB
        if not cls.is_experiment_eligible(project):
            return STRATEGY_JOB
        return requested

    @classmethod
    def requested_strategy(cls, project: Project) -> str:
        return getattr(project, "bedrock_ingestion_strategy", STRATEGY_JOB) or STRATEGY_JOB
