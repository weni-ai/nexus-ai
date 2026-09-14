from uuid import uuid4

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from nexus.event_domain.recent_activity.mocks import mock_event_manager_notify
from nexus.inline_agents.api.views import set_project_manager_agent
from nexus.inline_agents.backends.openai.models import ManagerAgent, ModelProvider
from nexus.projects.exceptions import ManagerChangeNotAllowedForLiveDeskCopilot
from nexus.projects.project_dto import ProjectCreationDTO
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.projects.projects_use_case import ProjectsUseCase
from nexus.usecases.projects.tests.project_factory import ProjectFactory


def _create_manager(name="Manager", public=True, default=False, **kwargs):
    defaults = dict(
        name=name,
        base_prompt="You are a manager.",
        foundation_model="gpt-4o",
        model_vendor="openai",
        release_date=timezone.now(),
        collaborators_foundation_model="gpt-4o-mini",
        formatter_agent_foundation_model="gpt-4o-mini",
        public=public,
        default=default,
    )
    defaults.update(kwargs)
    return ManagerAgent.objects.create(**defaults)


class TestCreateProjectLiveDeskCopilotFlag(TestCase):
    def test_create_project_persists_is_live_desk_copilot(self):
        org = OrgFactory()
        project_dto = ProjectCreationDTO(
            uuid=uuid4().hex,
            name="live_desk_copilot",
            org_uuid=org.uuid,
            is_template=False,
            template_type_uuid=None,
            brain_on=False,
            authorizations=[],
            is_live_desk_copilot=True,
        )

        project = ProjectsUseCase(event_manager_notify=mock_event_manager_notify).create_project(
            project_dto=project_dto, user_email=org.created_by.email
        )

        self.assertTrue(project.is_live_desk_copilot)

    def test_create_project_defaults_is_live_desk_copilot_false(self):
        org = OrgFactory()
        project_dto = ProjectCreationDTO(
            uuid=uuid4().hex,
            name="normal_project",
            org_uuid=org.uuid,
            is_template=False,
            template_type_uuid=None,
            brain_on=False,
            authorizations=[],
        )

        project = ProjectsUseCase(event_manager_notify=mock_event_manager_notify).create_project(
            project_dto=project_dto, user_email=org.created_by.email
        )

        self.assertFalse(project.is_live_desk_copilot)


class TestSetProjectManagerAgentLiveDeskCopilot(TestCase):
    def setUp(self):
        self.current_manager = _create_manager(name="Current", public=True, default=True)
        self.other_manager = _create_manager(name="Other", public=True)
        self.project = ProjectFactory(
            name="CopilotProject",
            is_live_desk_copilot=True,
            manager_agent=self.current_manager,
        )

    def test_blocks_manager_change_for_live_desk_copilot(self):
        with self.assertRaises(ManagerChangeNotAllowedForLiveDeskCopilot):
            set_project_manager_agent(str(self.project.uuid), str(self.other_manager.uuid))

        self.project.refresh_from_db()
        self.assertEqual(self.project.manager_agent_id, self.current_manager.id)

    def test_allows_idempotent_same_manager(self):
        result = set_project_manager_agent(str(self.project.uuid), str(self.current_manager.uuid))
        self.assertEqual(result, str(self.current_manager.uuid))
        self.project.refresh_from_db()
        self.assertEqual(self.project.manager_agent_id, self.current_manager.id)

    def test_allows_manager_change_for_normal_project(self):
        normal_project = ProjectFactory(
            name="NormalProject",
            is_live_desk_copilot=False,
            manager_agent=self.current_manager,
        )

        result = set_project_manager_agent(str(normal_project.uuid), str(self.other_manager.uuid))
        self.assertEqual(result, str(self.other_manager.uuid))
        normal_project.refresh_from_db()
        self.assertEqual(normal_project.manager_agent_id, self.other_manager.id)


class TestAgentManagersViewLiveDeskCopilot(TestCase):
    def setUp(self):
        self.current_manager = _create_manager(name="Current", public=True, default=True)
        self.other_manager = _create_manager(name="Other", public=True)
        self.project = ProjectFactory(
            name="CopilotAPIProject",
            is_live_desk_copilot=True,
            manager_agent=self.current_manager,
        )
        self.user = self.project.created_by
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = reverse("project-agent-managers", kwargs={"project_uuid": str(self.project.uuid)})

    def test_post_returns_403_when_changing_manager(self):
        response = self.client.post(self.url, data={"currentManager": str(self.other_manager.uuid)}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertIn("Live Desk copilot", response.json()["error"])
        self.project.refresh_from_db()
        self.assertEqual(self.project.manager_agent_id, self.current_manager.id)

    def test_get_returns_only_current_manager(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["currentManager"], str(self.current_manager.uuid))
        self.assertEqual(data["new"]["id"], str(self.current_manager.uuid))
        self.assertNotIn("legacy", data)


class TestModelProvidersViewLiveDeskCopilot(TestCase):
    def setUp(self):
        self.current_manager = _create_manager(name="Current", public=True, default=True)
        self.other_manager = _create_manager(name="Other", model_vendor="gemini")
        self.project = ProjectFactory(
            name="CopilotProviderProject",
            is_live_desk_copilot=True,
            manager_agent=self.current_manager,
        )
        self.other_provider = ModelProvider.objects.create(
            model_vendor="gemini",
            label="Google Gemini",
            credentials=[{"id": "api_key", "label": "API key", "type": "PASSWORD"}],
            manager_agent=self.other_manager,
        )
        self.user = self.project.created_by
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = reverse("project-model-providers", kwargs={"project_uuid": str(self.project.uuid)})

    def test_post_blocks_provider_that_changes_manager(self):
        response = self.client.post(
            self.url,
            data={
                "provider_uuid": str(self.other_provider.uuid),
                "credentials": [{"id": "api_key", "value": "secret"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.project.refresh_from_db()
        self.assertEqual(self.project.manager_agent_id, self.current_manager.id)

    def test_delete_blocks_manager_revert(self):
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 403)
        self.project.refresh_from_db()
        self.assertEqual(self.project.manager_agent_id, self.current_manager.id)
