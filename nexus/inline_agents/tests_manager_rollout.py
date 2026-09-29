from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from nexus.inline_agents.backends.openai.models import ManagerAgent
from nexus.inline_agents.manager_rollout import can_select_manager_via_api
from nexus.usecases.projects.tests.project_factory import ProjectFactory


def _create_manager(name: str, **kwargs) -> ManagerAgent:
    defaults = {
        "base_prompt": "You are a manager.",
        "foundation_model": "gpt-4o",
        "model_vendor": "openai",
        "release_date": timezone.now(),
        "collaborators_foundation_model": "gpt-4o-mini",
        "formatter_agent_foundation_model": "gpt-4o-mini",
        "public": True,
        "default": False,
    }
    defaults.update(kwargs)
    return ManagerAgent.objects.create(name=name, **defaults)


class TestCanSelectManagerViaApi(TestCase):
    def setUp(self):
        self.public = _create_manager("Manager 2.7", public=True)
        self.private = _create_manager("Manager 2.8", public=False, default=False)
        self.project = ProjectFactory(manager_agent=self.public)

    def test_public_manager_does_not_need_flag(self):
        with patch("nexus.inline_agents.manager_rollout.is_feature_active_for_attributes") as mock_flag:
            self.assertTrue(can_select_manager_via_api(self.public, self.project, "user@example.com"))
            mock_flag.assert_not_called()

    @patch("nexus.inline_agents.manager_rollout.is_feature_active_for_attributes", return_value=False)
    def test_private_manager_is_blocked_without_flag(self, mock_flag):
        self.assertFalse(can_select_manager_via_api(self.private, self.project, "user@example.com"))
        mock_flag.assert_called_once()

    @patch("nexus.inline_agents.manager_rollout.is_feature_active_for_attributes", return_value=True)
    def test_private_manager_is_allowed_with_flag(self, _mock_flag):
        self.assertTrue(can_select_manager_via_api(self.private, self.project, "user@example.com"))

    def test_already_assigned_private_manager_is_idempotent(self):
        self.project.manager_agent = self.private
        self.project.save(update_fields=["manager_agent"])
        with patch("nexus.inline_agents.manager_rollout.is_feature_active_for_attributes") as mock_flag:
            self.assertTrue(can_select_manager_via_api(self.private, self.project))
            mock_flag.assert_not_called()

    @patch(
        "nexus.inline_agents.manager_rollout.is_feature_active_for_attributes",
        side_effect=RuntimeError("GrowthBook down"),
    )
    def test_flag_evaluation_failure_denies_assignment(self, _mock_flag):
        self.assertFalse(can_select_manager_via_api(self.private, self.project))


class TestAgentManagersPrivateRollout(TestCase):
    def setUp(self):
        self.public = _create_manager("Manager 2.7", public=True)
        self.private = _create_manager("Manager 2.8", public=False, default=False)
        self.project = ProjectFactory(manager_agent=self.public)
        self.client = APIClient()
        self.client.force_authenticate(user=self.project.created_by)
        self.url = reverse("project-agent-managers", kwargs={"project_uuid": str(self.project.uuid)})

    def test_get_does_not_list_private_manager(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["new"]["id"], str(self.public.uuid))

    @patch("nexus.inline_agents.api.views.notify_async")
    @patch("nexus.inline_agents.manager_rollout.is_feature_active_for_attributes", return_value=False)
    def test_post_rejects_private_manager_without_flag(self, _mock_flag, mock_notify):
        response = self.client.post(self.url, {"currentManager": str(self.private.uuid)}, format="json")
        self.assertEqual(response.status_code, 404)
        self.project.refresh_from_db()
        self.assertEqual(self.project.manager_agent_id, self.public.id)
        mock_notify.assert_not_called()

    @patch("nexus.inline_agents.api.views.notify_async")
    @patch("nexus.inline_agents.manager_rollout.is_feature_active_for_attributes", return_value=True)
    def test_post_allows_private_manager_with_flag(self, _mock_flag, mock_notify):
        response = self.client.post(self.url, {"currentManager": str(self.private.uuid)}, format="json")
        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.manager_agent_id, self.private.id)
        mock_notify.assert_called_once()

    @patch("nexus.inline_agents.api.views.notify_async")
    def test_post_keeps_admin_assigned_private_manager(self, mock_notify):
        self.project.manager_agent = self.private
        self.project.save(update_fields=["manager_agent"])
        with patch("nexus.inline_agents.manager_rollout.is_feature_active_for_attributes") as mock_flag:
            response = self.client.post(self.url, {"currentManager": str(self.private.uuid)}, format="json")
            mock_flag.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["currentManager"], str(self.private.uuid))
        mock_notify.assert_called_once()

    def test_get_returns_admin_assigned_private_manager_as_current(self):
        self.project.manager_agent = self.private
        self.project.save(update_fields=["manager_agent"])
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["currentManager"], str(self.private.uuid))
        self.assertEqual(response.json()["new"]["id"], str(self.private.uuid))
        self.assertNotIn("legacy", response.json())
