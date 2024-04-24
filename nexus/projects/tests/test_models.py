from uuid import uuid4

from django.test import TestCase

from ..models import (
    Project,
    ProjectAuthorizationRole,
    ProjectAuth,
    TemplateType
)

from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.orgs.tests.org_factory import OrgFactory


class ProjectTestCase(TestCase):

    def setUp(self) -> None:
        self.org = OrgFactory()
        self.user = self.org.created_by

    def test_create_project(self):
        project = Project.objects.create(
            name="Test Project",
            org=self.org,
            created_by=self.user
        )

        self.assertEqual(project.name, "Test Project")
        self.assertEqual(project.org, self.org)
        self.assertEqual(project.created_by, self.user)
        self.assertFalse(project.brain_on)
        self.assertFalse(project.is_template)
        self.assertIsNone(project.template_type)


class ProjectAuthTestCase(TestCase):

    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.user = self.project.created_by

    def test_create_project_auth(self):
        project_auth = ProjectAuth.objects.create(
            project=self.project,
            user=self.user,
            role=ProjectAuthorizationRole.VIEWER.value
        )

        self.assertEqual(project_auth.project, self.project)
        self.assertEqual(project_auth.user, self.user)
        self.assertEqual(project_auth.role, ProjectAuthorizationRole.VIEWER.value)


class TemplateTypeTestCase(TestCase):

    def test_create_template_type(self):
        template_type = TemplateType.objects.create(
            name="Test Template Type",
            setup={},
            uuid=uuid4().hex
        )

        self.assertEqual(template_type.name, "Test Template Type")
        self.assertEqual(template_type.setup, {})
