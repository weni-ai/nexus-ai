from django.test import TestCase

from nexus.usecases.users.tests.user_factory import UserFactory
from nexus.usecases.users.exceptions import UserDoesNotExists

from ..create import CreateOrgUseCase


class CreateOrgTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.usecase = CreateOrgUseCase()
        self.org_name = 'Org Test'

    def test_create_org(self):
        org = self.usecase.create_orgs(self.user.email, self.org_name)

        self.assertEqual(org.name, self.org_name)

    def test_create_org_invalid_email(self):
        invalid_email: str = 'invalid@email.com'
        with self.assertRaises(UserDoesNotExists):
            self.usecase.create_orgs(invalid_email, self.org_name)
