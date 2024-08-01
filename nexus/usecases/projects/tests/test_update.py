from django.test import TestCase

from unittest.mock import patch

from nexus.usecases.projects.tests.project_factory import FeatureVersionFactory
from ..update import ProjectUpdateUseCase, UpdateFeatureVersionUseCase
from ..dto import UpdateProjectDTO, FeatureVersionDTO

from nexus.usecases.intelligences.tests.intelligence_factory import IntegratedIntelligenceFactory


class UpdateProjectTestCase(TestCase):

    def setUp(self) -> None:
        integrated_intelligence = IntegratedIntelligenceFactory()
        self.project = integrated_intelligence.project
        self.user = self.project.created_by
        self.uuid = self.project.uuid

    @patch("nexus.usecases.projects.update.update_message")
    def test_update_brain_on(self, mock_update_message):

        mock_update_message.return_value = None

        brain_on = True
        dto = UpdateProjectDTO(
            user_email=self.user.email,
            uuid=self.uuid,
            brain_on=brain_on
        )
        usecase = ProjectUpdateUseCase()
        updated_project = usecase.update_project(dto)
        self.assertEqual(updated_project.brain_on, brain_on)


class FeatureVersionTestCase(TestCase):

    def setUp(self) -> None:
        self.feature_version = FeatureVersionFactory()
        self.usecase = UpdateFeatureVersionUseCase()

    def test_update_feature_version(self):
        setup = {"test": "test"}
        dto = FeatureVersionDTO(
            uuid=self.feature_version.uuid,
            setup=setup
        )
        updated_feature_version = self.usecase.update_feature_version(dto)
        self.assertEqual(updated_feature_version.setup, setup)
