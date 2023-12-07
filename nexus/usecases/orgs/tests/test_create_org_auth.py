from django.test import TestCase

from nexus.usecases.orgs.tests.org_factory import OrgFactory

from ..create import create_org_auth


class TestCreateOrgAuthTestCase(TestCase):
    def setUp(self):
        self.org = OrgFactory()
        self.user = self.org.created_by

    def test_create_org_auth_admin(self):
        role: int = 3
        org_auth = create_org_auth(str(self.org.uuid), self.user.email, role)
        self.assertEqual(org_auth.user, self.user)
        self.assertEqual(org_auth.org, self.org)
        self.assertEqual(org_auth.role, role)
