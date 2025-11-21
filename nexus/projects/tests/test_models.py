from uuid import uuid4

from django.test import TestCase

from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from nexus.usecases.projects.tests.project_factory import ProjectFactory

from ..models import Project, ProjectAuth, ProjectAuthorizationRole, TemplateType


class ProjectTestCase(TestCase):
    def setUp(self) -> None:
        self.org = OrgFactory()
        self.user = self.org.created_by
        self.default_prompt_creation_configurations = {
            "use_prompt_creation_configurations": True,
            "conversation_turns_to_include": 10,
            "exclude_previous_thinking_steps": True,
        }
        self.project = ProjectFactory(project_auth=None)

    def test_create_project(self):
        project = Project.objects.create(name="Test Project", org=self.org, created_by=self.user)

        self.assertEqual(project.name, "Test Project")
        self.assertEqual(project.org, self.org)
        self.assertEqual(project.created_by, self.user)
        self.assertFalse(project.brain_on)
        self.assertFalse(project.is_template)
        self.assertIsNone(project.template_type)

    def test_set_project_prompt_creation_configurations(self):
        project_usecase = ProjectsUseCase()
        project_usecase.set_project_prompt_creation_configurations(
            project_uuid=self.project.uuid,
            use_prompt_creation_configurations=True,
            conversation_turns_to_include=10,
            exclude_previous_thinking_steps=True,
        )
        self.project.refresh_from_db()
        self.assertTrue(self.project.use_prompt_creation_configurations)
        self.assertTrue(self.project.exclude_previous_thinking_steps)
        self.assertEqual(self.project.conversation_turns_to_include, 10)

    def test_default_prompt_creation_configurations(self):
        self.assertTrue(self.project.use_prompt_creation_configurations)
        self.assertTrue(self.project.exclude_previous_thinking_steps)
        self.assertEqual(self.project.conversation_turns_to_include, 10)

    def test_get_project_prompt_creation_configurations(self):
        project_usecase = ProjectsUseCase()
        configurations = project_usecase.get_project_prompt_creation_configurations(project_uuid=self.project.uuid)
        self.assertEqual(configurations, self.default_prompt_creation_configurations)


class ProjectAuthTestCase(TestCase):
    def setUp(self) -> None:
        self.project = ProjectFactory(project_auth=None)
        self.user = self.project.created_by

    def test_create_project_auth(self):
        project_auth = ProjectAuth.objects.create(
            project=self.project, user=self.user, role=ProjectAuthorizationRole.VIEWER.value
        )

        self.assertEqual(project_auth.project, self.project)
        self.assertEqual(project_auth.user, self.user)
        self.assertEqual(project_auth.role, ProjectAuthorizationRole.VIEWER.value)


class TemplateTypeTestCase(TestCase):
    def test_create_template_type(self):
        template_type = TemplateType.objects.create(name="Test Template Type", setup={}, uuid=uuid4().hex)

        self.assertEqual(template_type.name, "Test Template Type")
        self.assertEqual(template_type.setup, {})
