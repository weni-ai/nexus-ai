from django.test import TestCase

from ..create import (
    CreateIntelligencesUseCase,
    CreateContentBaseUseCase,
    CreateContentBaseTextUseCase
)
from nexus.usecases.orgs.tests.org_factory import OrgFactory, OrgAuthFactory
from nexus.usecases.users.tests.user_factory import UserFactory
from nexus.usecases.intelligences.tests.intelligence_factory import (
    ContentBaseFactory,
)


class TestListIntelligenceUseCase(TestCase):

    def setUp(self):
        self.user = UserFactory()
        self.org = OrgFactory(created_by=self.user)
        self.auth = OrgAuthFactory(org=self.org, user=self.user)

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
        self.auth = OrgAuthFactory(org=self.org, user=self.user)
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

    def test_create_content_base_text_use_case(self):
        contentbase = ContentBaseFactory(
            intelligence=self.intelligence,
            created_by=self.user
        )
        use_case = CreateContentBaseTextUseCase()
        content_base_text_create = use_case.create_contentbasetext(
            contentbase_uuid=contentbase.uuid,
            user_email=self.user.email,
            text="text"
        )
        self.assertEqual(content_base_text_create.text, "text")
