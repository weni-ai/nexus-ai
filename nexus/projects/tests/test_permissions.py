from unittest import mock

from django.test.testcases import TestCase
from rest_framework.permissions import SAFE_METHODS

from nexus.projects.exceptions import ProjectAuthorizationDenied
from nexus.projects.models import ProjectAuth, ProjectAuthorizationRole
from nexus.projects.permissions import (
    _check_project_authorization,
    _has_project_general_permission,
    _user_email_from_authorization_payload,
    get_user_auth,
    is_admin,
    is_contributor,
    is_support,
)
from nexus.usecases.orgs.tests.org_factory import OrgAuthFactory
from nexus.usecases.projects.tests.project_factory import ProjectAuthFactory, ProjectFactory


class TestProjectPermissions(TestCase):
    def setUp(self) -> None:
        self.user_no_permission = ProjectAuthFactory()
        self.project = ProjectFactory()

        self.admin_auth = ProjectAuthFactory(project=self.project, role=ProjectAuthorizationRole.MODERATOR.value)
        self.viewer_auth = ProjectAuthFactory(project=self.project, role=ProjectAuthorizationRole.VIEWER.value)
        self.contributor_auth = ProjectAuthFactory(
            project=self.project, role=ProjectAuthorizationRole.CONTRIBUTOR.value
        )
        self.support_auth = ProjectAuthFactory(project=self.project, role=ProjectAuthorizationRole.SUPPORT.value)
        self.not_set_auth = ProjectAuthFactory(project=self.project, role=ProjectAuthorizationRole.NOT_SETTED.value)
        self.chat_user_auth = ProjectAuthFactory(project=self.project, role=ProjectAuthorizationRole.CHAT_USER.value)

    def test_is_admin(self):
        self.assertTrue(is_admin(self.admin_auth))
        self.assertFalse(is_admin(self.viewer_auth))
        self.assertFalse(is_admin(self.contributor_auth))
        self.assertFalse(is_admin(self.support_auth))
        self.assertFalse(is_admin(self.not_set_auth))
        self.assertFalse(is_admin(self.chat_user_auth))

    def test_is_contributor(self):
        self.assertTrue(is_contributor(self.contributor_auth))

        self.assertFalse(is_contributor(self.viewer_auth))
        self.assertFalse(is_contributor(self.admin_auth))
        self.assertFalse(is_contributor(self.support_auth))
        self.assertFalse(is_contributor(self.not_set_auth))
        self.assertFalse(is_contributor(self.chat_user_auth))

    def test_is_support(self):
        self.assertTrue(is_support(self.support_auth))

        self.assertFalse(is_support(self.viewer_auth))
        self.assertFalse(is_support(self.admin_auth))
        self.assertFalse(is_support(self.contributor_auth))
        self.assertFalse(is_support(self.not_set_auth))
        self.assertFalse(is_support(self.chat_user_auth))

    def test_has_project_general_permission(self):
        methods = ["POST", "PUT", "PATCH", "DELETE"]
        safe_methods = SAFE_METHODS

        for method in methods:
            self.assertTrue(_has_project_general_permission(self.admin_auth, method))
            self.assertTrue(_has_project_general_permission(self.contributor_auth, method))

            self.assertRaises(ProjectAuthorizationDenied, _has_project_general_permission, self.viewer_auth, method)
            self.assertRaises(ProjectAuthorizationDenied, _has_project_general_permission, self.support_auth, method)
            self.assertRaises(ProjectAuthorizationDenied, _has_project_general_permission, self.not_set_auth, method)
            self.assertRaises(ProjectAuthorizationDenied, _has_project_general_permission, self.chat_user_auth, method)

        for method in safe_methods:
            self.assertTrue(_has_project_general_permission(self.admin_auth, method))
            self.assertTrue(_has_project_general_permission(self.contributor_auth, method))
            self.assertTrue(_has_project_general_permission(self.viewer_auth, method))
            self.assertTrue(_has_project_general_permission(self.support_auth, method))
            self.assertTrue(_has_project_general_permission(self.not_set_auth, method))
            self.assertTrue(_has_project_general_permission(self.chat_user_auth, method))

    def test_get_user_exiting_auth(self):
        project = self.admin_auth.project
        user = self.admin_auth.user

        self.assertEqual(get_user_auth(user, project), self.admin_auth)

    def test_non_exiting_auth(self):
        project = self.admin_auth.project
        user = self.user_no_permission.user

        with self.assertRaises(ProjectAuth.DoesNotExist):
            get_user_auth(user, project)

    def test_existing_org_auth(self):
        org_auth = OrgAuthFactory()
        project = ProjectFactory(org=org_auth.org)

        created_project_auth = get_user_auth(org_auth.user, project)
        self.assertIsInstance(created_project_auth, ProjectAuth)

    def test_user_email_from_authorization_payload_with_email(self):
        email = _user_email_from_authorization_payload(
            {"user": {"email": "  someone@example.com  "}, "project_authorization": 3}
        )
        self.assertEqual(email, "someone@example.com")

    def test_user_email_from_authorization_payload_user_is_email_string(self):
        email = _user_email_from_authorization_payload({"user": "  caller@example.com  ", "project_authorization": 3})
        self.assertEqual(email, "caller@example.com")

    def test_user_email_from_authorization_payload_missing_or_invalid(self):
        self.assertIsNone(_user_email_from_authorization_payload({}))
        self.assertIsNone(_user_email_from_authorization_payload({"user": None}))
        self.assertIsNone(_user_email_from_authorization_payload({"user": "   "}))
        self.assertIsNone(_user_email_from_authorization_payload({"user": {"email": ""}}))
        self.assertIsNone(_user_email_from_authorization_payload({"user": {"email": 123}}))

    @mock.patch("nexus.projects.permissions.requests.get")
    def test_check_project_authorization_returns_email_for_moderator(self, mock_get):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "project_authorization": 3,
            "user": {"email": "moderator@example.com"},
        }
        mock_get.return_value = mock_response

        ok, email = _check_project_authorization("Bearer t", "project-uuid", "POST")
        self.assertTrue(ok)
        self.assertEqual(email, "moderator@example.com")

    @mock.patch("nexus.projects.permissions.requests.get")
    def test_check_project_authorization_returns_email_when_user_is_string(self, mock_get):
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "project_authorization": 3,
            "user": "moderator@example.com",
        }
        mock_get.return_value = mock_response

        ok, email = _check_project_authorization("Bearer t", "project-uuid", "POST")
        self.assertTrue(ok)
        self.assertEqual(email, "moderator@example.com")
