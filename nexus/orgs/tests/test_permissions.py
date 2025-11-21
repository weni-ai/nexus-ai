from django.test import TestCase

from nexus.orgs import permissions
from nexus.orgs.models import Role
from nexus.usecases.orgs.tests.org_factory import OrgAuthFactory

# TODO: Use parameterized tests


class TestAdminPermissionTestCase(TestCase):
    def setUp(self):
        self.admin_auth = OrgAuthFactory()
        self.user = self.admin_auth.user
        self.org = self.admin_auth.org

    def test_is_admin(self):
        self.assertTrue(permissions.is_admin(self.admin_auth))

    def test_can_contribute(self):
        self.assertTrue(permissions.can_contribute(self.admin_auth))

    def test_can_view(self):
        self.assertTrue(permissions.can_view(self.admin_auth))

    def test_can_create_intelligence_in_org(self):
        self.assertTrue(permissions.can_create_intelligence_in_org(self.user, self.org))

    def test_can_list_org_intelligences(self):
        self.assertTrue(permissions.can_list_org_intelligences(self.user, self.org))

    def test_can_edit_intelligence_of_org(self):
        self.assertTrue(permissions.can_edit_intelligence_of_org(self.user, self.org))

    def test_can_delete_intelligence_of_org(self):
        self.assertTrue(permissions.can_delete_intelligence_of_org(self.user, self.org))

    def test_can_list_content_bases(self):
        self.assertTrue(permissions.can_list_content_bases(self.user, self.org))

    def test_can_create_content_bases(self):
        self.assertTrue(permissions.can_create_content_bases(self.user, self.org))

    def test_can_add_content_base_file(self):
        self.assertTrue(permissions.can_add_content_base_file(self.user, self.org))

    def test_can_delete_content_base_file(self):
        self.assertTrue(permissions.can_delete_content_base_file(self.user, self.org))

    def test_can_test_content_base(self):
        self.assertTrue(permissions.can_test_content_base(self.user, self.org))

    def test_can_download_content_base_file(self):
        self.assertTrue(permissions.can_download_content_base_file(self.user, self.org))

    def test_get_user_auth(self):
        self.assertEqual(self.admin_auth, permissions.get_user_auth(self.user, self.org))


class TestContributorPermissionTestCase(TestCase):
    def setUp(self):
        self.contributor = OrgAuthFactory(role=Role.CONTRIBUTOR.value)
        self.user = self.contributor.user
        self.org = self.contributor.org

    def test_is_not_admin(self):
        self.assertFalse(permissions.is_admin(self.contributor))

    def test_can_contribute(self):
        self.assertTrue(permissions.can_contribute(self.contributor))

    def test_can_view(self):
        self.assertTrue(permissions.can_view(self.contributor))

    def test_can_create_intelligence_in_org(self):
        self.assertTrue(permissions.can_create_intelligence_in_org(self.user, self.org))

    def test_can_list_org_intelligences(self):
        self.assertTrue(permissions.can_list_org_intelligences(self.user, self.org))

    def test_can_edit_intelligence_of_org(self):
        self.assertTrue(permissions.can_edit_intelligence_of_org(self.user, self.org))

    def test_cant_delete_intelligence_of_org(self):
        self.assertFalse(permissions.can_delete_intelligence_of_org(self.user, self.org))

    def test_can_list_content_bases(self):
        self.assertTrue(permissions.can_list_content_bases(self.user, self.org))

    def test_can_create_content_bases(self):
        self.assertTrue(permissions.can_create_content_bases(self.user, self.org))

    def test_can_add_content_base_file(self):
        self.assertTrue(permissions.can_add_content_base_file(self.user, self.org))

    def test_can_delete_content_base_file(self):
        self.assertTrue(permissions.can_delete_content_base_file(self.user, self.org))

    def test_can_test_content_base(self):
        self.assertTrue(permissions.can_test_content_base(self.user, self.org))

    def test_can_download_content_base_file(self):
        self.assertTrue(permissions.can_download_content_base_file(self.user, self.org))


class TestViewerPermissionTestCase(TestCase):
    def setUp(self):
        self.viewer_auth = OrgAuthFactory(role=Role.VIEWER.value)
        self.user = self.viewer_auth.user
        self.org = self.viewer_auth.org

    def test_is_not_admin(self):
        self.assertFalse(permissions.is_admin(self.viewer_auth))

    def test_cant_contribute(self):
        self.assertFalse(permissions.can_contribute(self.viewer_auth))

    def test_can_view(self):
        self.assertTrue(permissions.can_view(self.viewer_auth))

    def test_cant_create_intelligence_in_org(self):
        self.assertFalse(permissions.can_create_intelligence_in_org(self.user, self.org))

    def test_cant_list_org_intelligences(self):
        self.assertTrue(permissions.can_list_org_intelligences(self.user, self.org))

    def test_cant_edit_intelligence_of_org(self):
        self.assertFalse(permissions.can_edit_intelligence_of_org(self.user, self.org))

    def test_cant_delete_intelligence_of_org(self):
        self.assertFalse(permissions.can_delete_intelligence_of_org(self.user, self.org))

    def test_can_list_content_bases(self):
        self.assertTrue(permissions.can_list_content_bases(self.user, self.org))

    def test_cant_create_content_bases(self):
        self.assertFalse(permissions.can_create_content_bases(self.user, self.org))

    def test_cant_add_content_base_file(self):
        self.assertFalse(permissions.can_add_content_base_file(self.user, self.org))

    def test_cant_delete_content_base_file(self):
        self.assertFalse(permissions.can_delete_content_base_file(self.user, self.org))

    def test_cant_test_content_base(self):
        self.assertFalse(permissions.can_test_content_base(self.user, self.org))

    def test_cant_download_content_base_file(self):
        self.assertFalse(permissions.can_download_content_base_file(self.user, self.org))


class TestOrgAuthDoesNotExist(TestCase):
    def setUp(self) -> None:
        self.user = OrgAuthFactory().user
        self.org = OrgAuthFactory().org

    def test_can_create_intelligence_in_org(self):
        self.assertFalse(permissions.can_create_intelligence_in_org(self.user, self.org))

    def test_can_list_org_intelligences(self):
        self.assertFalse(permissions.can_list_org_intelligences(self.user, self.org))

    def test_can_edit_intelligence_of_org(self):
        self.assertFalse(permissions.can_edit_intelligence_of_org(self.user, self.org))

    def test_can_delete_intelligence_of_org(self):
        self.assertFalse(permissions.can_delete_intelligence_of_org(self.user, self.org))

    def test_can_list_content_bases(self):
        self.assertFalse(permissions.can_list_content_bases(self.user, self.org))

    def test_can_create_content_bases(self):
        self.assertFalse(permissions.can_create_content_bases(self.user, self.org))

    def test_can_delete_content_bases(self):
        self.assertFalse(permissions.can_delete_content_bases(self.user, self.org))

    def test_can_edit_content_bases(self):
        self.assertFalse(permissions.can_edit_content_bases(self.user, self.org))

    def test_can_add_content_base_file(self):
        self.assertFalse(permissions.can_add_content_base_file(self.user, self.org))

    def test_can_delete_content_base_file(self):
        self.assertFalse(permissions.can_delete_content_base_file(self.user, self.org))

    def test_can_test_content_base(self):
        self.assertFalse(permissions.can_test_content_base(self.user, self.org))

    def test_can_download_content_base_file(self):
        self.assertFalse(permissions.can_download_content_base_file(self.user, self.org))
