from django.test.testcases import TestCase

from rest_framework.permissions import SAFE_METHODS

from nexus.usecases.projects.tests.project_factory import ProjectFactory, ProjectAuthFactory

from nexus.usecases.users.tests.user_factory import UserFactory
from nexus.usecases.orgs.tests.org_factory import OrgAuthFactory

from nexus.projects.models import ProjectAuthorizationRole, ProjectAuth
from nexus.projects.exceptions import ProjectAuthorizationDenied
from nexus.projects.permissions import (
    get_user_auth,
    is_admin,
    is_contributor,
    is_support,
    _has_project_general_permission,
    has_project_permission,
)

from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission


class TestProjectPermissions(TestCase):

    def setUp(self) -> None:
        self.user_no_permission = ProjectAuthFactory()
        self.project = ProjectFactory()

        self.admin_auth = ProjectAuthFactory(
            project=self.project,
            role=ProjectAuthorizationRole.MODERATOR.value
        )
        self.viewer_auth = ProjectAuthFactory(
            project=self.project,
            role=ProjectAuthorizationRole.VIEWER.value
        )
        self.contributor_auth = ProjectAuthFactory(
            project=self.project,
            role=ProjectAuthorizationRole.CONTRIBUTOR.value
        )
        self.support_auth = ProjectAuthFactory(
            project=self.project,
            role=ProjectAuthorizationRole.SUPPORT.value
        )
        self.not_set_auth = ProjectAuthFactory(
            project=self.project,
            role=ProjectAuthorizationRole.NOT_SETTED.value
        )
        self.chat_user_auth = ProjectAuthFactory(
            project=self.project,
            role=ProjectAuthorizationRole.CHAT_USER.value
        )

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

        methods = ['POST', 'PUT', 'PATCH', 'DELETE']
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

    def test_user_with_can_communicate_internally_permission(self):

        user = UserFactory()
        content_type = ContentType.objects.get_for_model(user)
        permission, created = Permission.objects.get_or_create(
            codename="can_communicate_internally",
            name="can communicate internally",
            content_type=content_type,
        )
        user.user_permissions.add(permission)
        project = ProjectFactory()

        self.assertTrue(has_project_permission(user, project, 'GET', module_perm=True))
        self.assertTrue(has_project_permission(user, project, 'POST', module_perm=True))
        self.assertTrue(has_project_permission(user, project, 'PUT', module_perm=True))
        self.assertTrue(has_project_permission(user, project, 'PATCH', module_perm=True))
        self.assertTrue(has_project_permission(user, project, 'DELETE', module_perm=True))
