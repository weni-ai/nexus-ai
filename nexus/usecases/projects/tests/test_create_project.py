from uuid import uuid4
from django.test import TestCase

from .project_factory import ProjectFactory
from ..projects_use_case import ProjectsUseCase
from nexus.projects.project_dto import ProjectCreationDTO
from nexus.usecases.event_driven.mocks import mock_recent_activity_message
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.projects.create import ProjectAuthUseCase
from nexus.usecases.users.tests.user_factory import UserFactory


class TestCreateProject(TestCase):

    def setUp(self) -> None:
        org = OrgFactory()
        self.user = org.created_by
        self.project_dto = ProjectCreationDTO(
            uuid=uuid4().hex,
            name="test_name",
            org_uuid=org.uuid,
            is_template=False,
            template_type_uuid=None,
        )

    def test_create_project(self):
        project = ProjectsUseCase(
            intelligence_activity_message=mock_recent_activity_message
        ).create_project(
            project_dto=self.project_dto,
            user_email=self.user.email
        )
        self.assertEqual(project.uuid, self.project_dto.uuid)
        mock_recent_activity_message.assert_called_once()


class ProjectAuthUseCaseTestCase(TestCase):

    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.user_email = UserFactory().email

    def test_create_project_auth(self):
        consumer_msg = {
            'project_uuid': str(self.project.uuid),
            'role': 3,
            'user_email': self.user_email
        }
        project_auth = ProjectAuthUseCase().create_project_auth(
            consumer_msg
        )
        self.assertEqual(project_auth.project, self.project)
        self.assertEqual(project_auth.user.email, self.user_email)
        self.assertEqual(project_auth.role, 3)
