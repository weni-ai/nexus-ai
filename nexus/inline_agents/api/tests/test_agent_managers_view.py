from unittest.mock import patch

import pendulum
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from nexus.inline_agents.api.views import AgentManagersView
from nexus.usecases.inline_agents.tests.manager_agent_factory import ManagerAgentFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class AgentManagersViewTests(TestCase):
    def setUp(self):
        self.project = ProjectFactory()
        self.factory = APIRequestFactory()
        self.view = AgentManagersView.as_view()
        self.user = self.project.created_by

    @patch("nexus.projects.api.permissions.has_external_general_project_permission", return_value=True)
    def test_get_returns_new_and_legacy_when_two_public_managers(self, _mock_permission):
        legacy_release = pendulum.datetime(2026, 3, 19, 19, 8, 22, tz="UTC")
        legacy = ManagerAgentFactory(name="Manager 2.5", public=True, release_date=legacy_release)
        new = ManagerAgentFactory(name="Manager 2.6", public=True, release_date=pendulum.now())
        self.project.manager_agent = new
        self.project.save(update_fields=["manager_agent"])

        request = self.factory.get(f"/project/{self.project.uuid}/managers")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, 200)
        self.assertIn("serverTime", response.data)
        self.assertEqual(response.data["new"]["id"], str(new.uuid))
        self.assertEqual(response.data["new"]["label"], "Manager 2.6")
        self.assertEqual(response.data["legacy"]["id"], str(legacy.uuid))
        self.assertEqual(response.data["legacy"]["label"], "Manager 2.5")
        self.assertEqual(
            response.data["legacy"]["deprecation"], pendulum.instance(new.release_date).to_iso8601_string()
        )
        self.assertEqual(response.data["currentManager"], str(new.uuid))

    @patch("nexus.projects.api.permissions.has_external_general_project_permission", return_value=True)
    def test_get_returns_only_new_when_single_public_manager(self, _mock_permission):
        new = ManagerAgentFactory(name="Manager 2.6", public=True, release_date=pendulum.now())
        self.project.manager_agent = new
        self.project.save(update_fields=["manager_agent"])

        request = self.factory.get(f"/project/{self.project.uuid}/managers")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, 200)
        self.assertIn("serverTime", response.data)
        self.assertEqual(response.data["new"]["id"], str(new.uuid))
        self.assertNotIn("legacy", response.data)
        self.assertEqual(response.data["currentManager"], str(new.uuid))

    @patch("nexus.projects.api.permissions.has_external_general_project_permission", return_value=True)
    def test_get_returns_only_current_manager_when_project_manager_is_private(self, _mock_permission):
        private_manager = ManagerAgentFactory(name="Private Manager", public=False, release_date=pendulum.now())
        ManagerAgentFactory(name="Manager 2.6", public=True, release_date=pendulum.now())
        ManagerAgentFactory(name="Manager 2.5", public=True, release_date=pendulum.now().subtract(days=1))
        self.project.manager_agent = private_manager
        self.project.save(update_fields=["manager_agent"])

        request = self.factory.get(f"/project/{self.project.uuid}/managers")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, 200)
        self.assertIn("serverTime", response.data)
        self.assertEqual(response.data["currentManager"], str(private_manager.uuid))
        self.assertNotIn("new", response.data)
        self.assertNotIn("legacy", response.data)

    @patch("nexus.projects.api.permissions.has_external_general_project_permission", return_value=True)
    def test_get_without_current_manager_does_not_include_current_manager(self, _mock_permission):
        ManagerAgentFactory(name="Manager 2.6", public=True, release_date=pendulum.now())
        ManagerAgentFactory(name="Manager 2.5", public=True, release_date=pendulum.now().subtract(days=1))
        self.project.manager_agent = None
        self.project.save(update_fields=["manager_agent"])

        request = self.factory.get(f"/project/{self.project.uuid}/managers")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, 200)
        self.assertIn("serverTime", response.data)
        self.assertIn("new", response.data)
        self.assertIn("legacy", response.data)
        self.assertNotIn("currentManager", response.data)

    @patch("nexus.projects.api.permissions.has_external_general_project_permission", return_value=True)
    def test_get_without_public_managers_returns_server_time_only(self, _mock_permission):
        self.project.manager_agent = None
        self.project.save(update_fields=["manager_agent"])

        request = self.factory.get(f"/project/{self.project.uuid}/managers")
        force_authenticate(request, user=self.user)
        response = self.view(request, project_uuid=self.project.uuid)

        self.assertEqual(response.status_code, 200)
        self.assertIn("serverTime", response.data)
        self.assertEqual(set(response.data.keys()), {"serverTime"})
