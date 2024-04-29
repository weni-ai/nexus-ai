from uuid import uuid4
from django.test import TestCase

from nexus.usecases.orgs.tests.org_factory import OrgFactory
from ..projects_use_case import ProjectsUseCase
from nexus.projects.project_dto import ProjectCreationDTO
from nexus.usecases.event_driven.mocks import mock_recent_activity_message


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
