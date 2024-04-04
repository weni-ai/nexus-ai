from django.test import TestCase
from .project_factory import ProjectFactory
from ..update import update_project
from ..dto import UpdateProjectDTO


class UpdateProjectTestCase(TestCase):

    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.user = self.project.created_by
        self.uuid = self.project.uuid

    def test_update_brain_on(self):
        brain_on = True
        dto = UpdateProjectDTO(
            user_email=self.user.email,
            uuid=self.uuid,
            brain_on=brain_on
        )
        updated_project = update_project(dto)
        self.assertEqual(updated_project.brain_on, brain_on)
