from django.test import TestCase

from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.orgs.create_org_auth import CreateOrgAuthUseCase

from nexus.orgs import permissions
from nexus.orgs.models import Role

# TODO: Use parameterized tests


class TestAdminPermissionTestCase(TestCase):
    def setUp(self):
        self.org = OrgFactory()
        self.user = self.org.created_by
        self.admin_auth = CreateOrgAuthUseCase().create_org_auth(str(self.org.uuid), self.org.created_by, role=Role.ADMIN.value)

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


class TestContributorPermissionTestCase(TestCase):
    def setUp(self):
        self.org = OrgFactory()
        self.user = self.org.created_by
        self.admin_auth = CreateOrgAuthUseCase().create_org_auth(str(self.org.uuid), self.org.created_by, role=Role.CONTRIBUTOR.value)

    def test_is_not_admin(self):
        self.assertFalse(permissions.is_admin(self.admin_auth))

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
        self.org = OrgFactory()
        self.user = self.org.created_by
        self.admin_auth = CreateOrgAuthUseCase().create_org_auth(str(self.org.uuid), self.org.created_by, role=Role.VIEWER.value)

    def test_is_not_admin(self):
        self.assertFalse(permissions.is_admin(self.admin_auth))

    def test_cant_contribute(self):
        self.assertFalse(permissions.can_contribute(self.admin_auth))

    def test_can_view(self):
        self.assertTrue(permissions.can_view(self.admin_auth))

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
