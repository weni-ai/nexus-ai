from django.test import SimpleTestCase, override_settings

from nexus.projects.models import Project
from nexus.task_managers.ingestion.constants import STRATEGY_DIRECT_WITH_FALLBACK, STRATEGY_JOB
from nexus.task_managers.ingestion.strategy import IngestionStrategyResolver


class IngestionStrategyResolverTest(SimpleTestCase):
    def _project(self, strategy: str = STRATEGY_DIRECT_WITH_FALLBACK) -> Project:
        return Project(bedrock_ingestion_strategy=strategy, uuid="11111111-1111-1111-1111-111111111111")

    def test_default_requested_job(self):
        project = Project(bedrock_ingestion_strategy=STRATEGY_JOB)
        self.assertEqual(IngestionStrategyResolver.resolve(project), STRATEGY_JOB)

    @override_settings(ENVIRONMENT="staging")
    def test_staging_allows_non_job_strategy(self):
        project = self._project()
        self.assertEqual(IngestionStrategyResolver.resolve(project), STRATEGY_DIRECT_WITH_FALLBACK)

    @override_settings(ENVIRONMENT="production", BEDROCK_DIRECT_INGESTION_PROJECT_ALLOWLIST=[])
    def test_production_non_allowlisted_forces_job(self):
        project = self._project()
        self.assertEqual(IngestionStrategyResolver.resolve(project), STRATEGY_JOB)

    @override_settings(
        ENVIRONMENT="production",
        BEDROCK_DIRECT_INGESTION_PROJECT_ALLOWLIST=["11111111-1111-1111-1111-111111111111"],
    )
    def test_allowlisted_production_project(self):
        project = self._project()
        self.assertEqual(IngestionStrategyResolver.resolve(project), STRATEGY_DIRECT_WITH_FALLBACK)
