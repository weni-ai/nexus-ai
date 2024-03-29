from django.test import TestCase

from nexus.usecases.users.tests.user_factory import UserFactory
from nexus.orgs.org_dto import OrgCreationDTO

from ..create import CreateOrgUseCase


class CreateOrgTestCase(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.usecase = CreateOrgUseCase()
        self.org_dto = OrgCreationDTO(
            uuid='d589c4d7-e664-4e1e-89ff-2cb2f1e9c4b2',
            name='Org Test',
            authorizations=[]
        )

    def test_create_org(self):
        org = self.usecase.create_orgs(user_email=self.user.email, org_dto=self.org_dto)

        self.assertEqual(org.name, self.org_dto.name)
