from django.test import TestCase

from unittest.mock import patch

from ..update import ProjectUpdateUseCase
from ..dto import UpdateProjectDTO

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
