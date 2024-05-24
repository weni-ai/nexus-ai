from django.test import TestCase
from uuid import uuid4

from .project_factory import ProjectFactory
from ..projects_use_case import ProjectsUseCase

from nexus.usecases.users.tests.user_factory import UserFactory

from nexus.usecases.projects.retrieve import get_project
from nexus.projects.exceptions import (
    ProjectAuthorizationDenied,
    ProjectDoesNotExist,
)

from nexus.usecases.projects.get_by_uuid import get_project_by_uuid


class GetByProjectUuidTestCase(TestCase):

    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.user = UserFactory()

    def test_get_by_uuid(self):
        retrieved_project = ProjectsUseCase().get_by_uuid(
            self.project.uuid
        )
        self.assertEqual(self.project, retrieved_project)

    def test_non_existent_project(self):
        with self.assertRaises(ProjectDoesNotExist):
            ProjectsUseCase().get_by_uuid(str(uuid4()))

    def test_invalid_uuid(self):
        with self.assertRaises(Exception):
            ProjectsUseCase().get_by_uuid("invalid_uuid")

    def test_get_project(self):
        self.project.authorizations.create(user=self.user, role=3)
        project = get_project(str(self.project.uuid), self.user.email)
        self.assertEqual(self.project, project)

    def test_fail_get_project(self):
        with self.assertRaises(ProjectAuthorizationDenied):
            get_project(str(self.project.uuid), self.user.email)

    def test_get_by_uuid_non_existent_project(self):
        with self.assertRaises(ProjectDoesNotExist):
            get_project_by_uuid(str(uuid4()))
