from django.test import TestCase

from ..create import (
    CreateIntelligencesUseCase,
    CreateContentBaseUseCase
)
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.users.tests.user_factory import UserFactory


class TestListIntelligenceUseCase(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.org = OrgFactory(created_by=self.user)

    def test_create_intelligence_use_case(self):
        use_case = CreateIntelligencesUseCase()
        intelligences_create = use_case.create_intelligences(
            name="name",
            description="description",
            org_uuid=self.org.uuid,
            user_email=self.user.email
        )
        self.assertEqual(intelligences_create.name, "name")


class TestCreateContentBaseUseCase(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.org = OrgFactory(created_by=self.user)
        self.intelligence = CreateIntelligencesUseCase().create_intelligences(
            name="name",
            description="description",
            org_uuid=self.org.uuid,
            user_email=self.user.email
        )

    def test_create_content_base_use_case(self):
        use_case = CreateContentBaseUseCase()
        content_base_create = use_case.create_contentbase(
            intelligence_uuid=self.intelligence.uuid,
            user_email=self.user.email,
            title="title"
        )
        self.assertEqual(content_base_create.title, "title")
