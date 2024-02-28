from django.test import TestCase
from uuid import uuid4

from .project_factory import ProjectFactory
from ..projects_use_case import ProjectsUseCase


class GetByProjectUuidTestCase(TestCase):

    def setUp(self) -> None:
        self.project = ProjectFactory()

    def test_get_by_uuid(self):
        retrieved_project = ProjectsUseCase().get_by_uuid(
            self.project.uuid
        )
        self.assertEqual(self.project, retrieved_project)

    def test_non_existent_project(self):
        with self.assertRaises(Exception):
            ProjectsUseCase().get_by_uuid(uuid4().hex)

    def test_invalid_uuid(self):
        with self.assertRaises(Exception):
            ProjectsUseCase().get_by_uuid("invalid_uuid")