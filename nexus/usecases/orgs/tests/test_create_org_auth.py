from django.test import TestCase

from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.orgs.exceptions import (
    OrgRoleDoesNotExists,
    OrgDoesNotExists,
)
from nexus.usecases.users.exceptions import UserDoesNotExists

from ..create import create_org_auth
from uuid import uuid4


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

    def test_create_org_auth_contributor(self):
        role: int = 2
        org_auth = create_org_auth(str(self.org.uuid), self.user.email, role)
        self.assertEqual(org_auth.user, self.user)
        self.assertEqual(org_auth.org, self.org)
        self.assertEqual(org_auth.role, role)

    def test_create_org_auth_viewer(self):
        role: int = 2
        org_auth = create_org_auth(str(self.org.uuid), self.user.email, role)
        self.assertEqual(org_auth.user, self.user)
        self.assertEqual(org_auth.org, self.org)
        self.assertEqual(org_auth.role, role)

    def test_create_org_auth_invalid_role(self):
        with self.assertRaises(OrgRoleDoesNotExists):
            role: int = 6
            create_org_auth(str(self.org.uuid), self.user.email, role)

    def test_create_org_auth_invalid_org_uuid(self):
        role: int = 3
        with self.assertRaises(OrgDoesNotExists):
            uuid: str = str(uuid4())
            create_org_auth(uuid, self.user.email, role=role)

    def test_create_org_auth_invalid_user_email(self):
        role: int = 3
        with self.assertRaises(UserDoesNotExists):
            invalid_email: str = 'invalid@email.com'
            create_org_auth(str(self.org.uuid), invalid_email, role=role)
