from django.test import TestCase

from .org_factory import OrgAuthFactory, OrgFactory
from ..get_org_auth import GetOrgAuthUseCase
from nexus.orgs.models import OrgAuth
from nexus.usecases.orgs.exceptions import OrgAuthDoesNotExists


class TestGetOrgAuth(TestCase):

    def setUp(self) -> None:
        self.org_auth = OrgAuthFactory()
        self.user = self.org_auth.user
        self.org = self.org_auth.org

    def test_get_org_auth_by_user(self):
        org_auth = GetOrgAuthUseCase().get_org_auth_by_user(self.user, self.org)
        self.assertEqual(org_auth, self.org_auth)

    def test_get_org_auth_by_user_not_exists(self):
        org_without_auth = OrgFactory()
        with self.assertRaises(OrgAuthDoesNotExists):
            GetOrgAuthUseCase().get_org_auth_by_user(self.user, org_without_auth)
