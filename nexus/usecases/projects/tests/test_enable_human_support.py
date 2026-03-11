from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase

from nexus.event_domain.recent_activity.mocks import mock_event_manager_notify
from nexus.projects.exceptions import ProjectDoesNotExist
from nexus.usecases.projects.projects_use_case import ProjectsUseCase

from .project_factory import ProjectFactory


class EnableHumanSupportTestCase(TestCase):
    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.usecase = ProjectsUseCase(
            event_manager_notify=mock_event_manager_notify,
        )

    def test_enable_human_support_true(self):
        """Test enabling human_support (True)"""
        self.project.human_support = False
        self.project.save()

        updated_project = self.usecase.enable_human_support(str(self.project.uuid), True)

        self.assertTrue(updated_project.human_support)

        self.project.refresh_from_db()
        self.assertTrue(self.project.human_support)

    def test_enable_human_support_false(self):
        """Test disabling human_support (False)"""
        self.project.human_support = True
        self.project.save()

        updated_project = self.usecase.enable_human_support(str(self.project.uuid), False)

        self.assertFalse(updated_project.human_support)

        self.project.refresh_from_db()
        self.assertFalse(self.project.human_support)

    def test_enable_human_support_nonexistent_project(self):
        """Test enabling human_support for non-existent project should raise an exception"""
        with self.assertRaises(ProjectDoesNotExist):
            self.usecase.enable_human_support(str(uuid4()), True)

    def test_enable_human_support_invalid_uuid(self):
        """Test enabling human_support with invalid UUID should raise an exception"""
        with self.assertRaises(Exception):  # noqa: B017
            self.usecase.enable_human_support("invalid_uuid", True)

    @patch("nexus.usecases.projects.projects_use_case.notify_async")
    def test_enable_human_support_calls_cache_invalidation(self, mock_notify_async):
        """Test that enabling human_support triggers cache invalidation event"""
        self.usecase.enable_human_support(str(self.project.uuid), True)

        mock_notify_async.assert_called_once()
        call_kwargs = mock_notify_async.call_args
        self.assertEqual(call_kwargs.kwargs.get("event"), "cache_invalidation:project")
        self.assertEqual(call_kwargs.kwargs.get("project").uuid, self.project.uuid)

    def test_enable_human_support_toggle_multiple_times(self):
        """Test toggling human_support multiple times"""
        self.project.human_support = False
        self.project.save()

        result1 = self.usecase.enable_human_support(str(self.project.uuid), True)
        self.assertTrue(result1.human_support)

        result2 = self.usecase.enable_human_support(str(self.project.uuid), False)
        self.assertFalse(result2.human_support)

        self.project.refresh_from_db()
        self.assertFalse(self.project.human_support)

    def test_update_human_support_prompt(self):
        """Test updating human_support_prompt"""
        new_prompt = "New human support prompt"
        self.project.human_support_prompt = None
        self.project.save()

        updated_project = self.usecase.update_human_support_prompt(str(self.project.uuid), new_prompt)

        self.assertEqual(updated_project.human_support_prompt, new_prompt)

        self.project.refresh_from_db()
        self.assertEqual(self.project.human_support_prompt, new_prompt)

    def test_update_human_support_prompt_empty_string(self):
        """Test updating human_support_prompt with empty string"""
        self.project.human_support_prompt = "Old prompt"
        self.project.save()

        updated_project = self.usecase.update_human_support_prompt(str(self.project.uuid), "")

        self.assertEqual(updated_project.human_support_prompt, "")

        self.project.refresh_from_db()
        self.assertEqual(self.project.human_support_prompt, "")

    def test_update_human_support_prompt_nonexistent_project(self):
        """Test updating human_support_prompt for non-existent project should raise an exception"""
        with self.assertRaises(ProjectDoesNotExist):
            self.usecase.update_human_support_prompt(str(uuid4()), "Some prompt")

    @patch("nexus.usecases.projects.projects_use_case.notify_async")
    def test_update_human_support_prompt_calls_cache_invalidation(self, mock_notify_async):
        """Test that updating human_support_prompt triggers cache invalidation event"""
        self.usecase.update_human_support_prompt(str(self.project.uuid), "New prompt")

        mock_notify_async.assert_called_once()
        call_kwargs = mock_notify_async.call_args
        self.assertEqual(call_kwargs.kwargs.get("event"), "cache_invalidation:project")
        self.assertEqual(call_kwargs.kwargs.get("project").uuid, self.project.uuid)

    def test_update_human_support_config_human_support_only(self):
        """Test update_human_support_config with only human_support"""
        self.project.human_support = False
        self.project.save()

        updated_project = self.usecase.update_human_support_config(str(self.project.uuid), human_support=True)

        self.assertTrue(updated_project.human_support)

        self.project.refresh_from_db()
        self.assertTrue(self.project.human_support)

    def test_update_human_support_config_prompt_only(self):
        """Test update_human_support_config with only human_support_prompt"""
        new_prompt = "New prompt"
        self.project.human_support_prompt = None
        self.project.save()

        updated_project = self.usecase.update_human_support_config(
            str(self.project.uuid), human_support_prompt=new_prompt
        )

        self.assertEqual(updated_project.human_support_prompt, new_prompt)

        self.project.refresh_from_db()
        self.assertEqual(self.project.human_support_prompt, new_prompt)

    def test_update_human_support_config_both_fields(self):
        """Test update_human_support_config with both fields"""
        new_prompt = "Updated prompt"
        self.project.human_support = False
        self.project.human_support_prompt = "Old prompt"
        self.project.save()

        updated_project = self.usecase.update_human_support_config(
            str(self.project.uuid), human_support=True, human_support_prompt=new_prompt
        )

        self.assertTrue(updated_project.human_support)
        self.assertEqual(updated_project.human_support_prompt, new_prompt)

        self.project.refresh_from_db()
        self.assertTrue(self.project.human_support)
        self.assertEqual(self.project.human_support_prompt, new_prompt)

    def test_update_human_support_config_no_fields(self):
        """Test update_human_support_config with no fields (should not change anything)"""
        original_support = self.project.human_support
        original_prompt = self.project.human_support_prompt
        self.project.save()

        updated_project = self.usecase.update_human_support_config(str(self.project.uuid))

        self.assertEqual(updated_project.human_support, original_support)
        self.assertEqual(updated_project.human_support_prompt, original_prompt)

        self.project.refresh_from_db()
        self.assertEqual(self.project.human_support, original_support)
        self.assertEqual(self.project.human_support_prompt, original_prompt)

    def test_update_human_support_config_nonexistent_project(self):
        """Test update_human_support_config for non-existent project should raise an exception"""
        with self.assertRaises(ProjectDoesNotExist):
            self.usecase.update_human_support_config(str(uuid4()), human_support=True)

    @patch("nexus.usecases.projects.projects_use_case.notify_async")
    def test_update_human_support_config_calls_cache_invalidation(self, mock_notify_async):
        """Test that update_human_support_config triggers cache invalidation event"""
        self.usecase.update_human_support_config(str(self.project.uuid), human_support=True)

        mock_notify_async.assert_called_once()
        call_kwargs = mock_notify_async.call_args
        self.assertEqual(call_kwargs.kwargs.get("event"), "cache_invalidation:project")
        self.assertEqual(call_kwargs.kwargs.get("project").uuid, self.project.uuid)
