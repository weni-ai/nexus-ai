from django.test import TestCase

from ..create import (
    CreateIntelligencesUseCase,
    CreateContentBaseUseCase,
    CreateContentBaseTextUseCase
)
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.intelligences.tests.intelligence_factory import (
    ContentBaseFactory,
)


class TestListIntelligenceUseCase(TestCase):

    def setUp(self):
        self.org = OrgFactory()

    def test_create_intelligence_use_case(self):
        use_case = CreateIntelligencesUseCase()
        intelligences_create = use_case.create_intelligences(
            name="name",
            description="description",
            org_uuid=self.org.uuid,
            user_email=self.org.created_by
        )
        self.assertEqual(intelligences_create.name, "name")


class TestCreateContentBaseUseCase(TestCase):

    def setUp(self):
        self.org = OrgFactory()
        self.intelligence = CreateIntelligencesUseCase().create_intelligences(
            name="name",
            description="description",
            org_uuid=self.org.uuid,
            user_email=self.org.created_by
        )

    def test_create_content_base_use_case(self):
        use_case = CreateContentBaseUseCase()
        content_base_create = use_case.create_contentbase(
            intelligence_uuid=self.intelligence.uuid,
            user_email=self.org.created_by,
            title="title"
        )
        self.assertEqual(content_base_create.title, "title")

    def test_create_content_base_text_use_case(self):
        contentbase = ContentBaseFactory()
        use_case = CreateContentBaseTextUseCase()
        content_base_text_create = use_case.create_contentbasetext(
            contentbase_uuid=contentbase.uuid,
            user_email=contentbase.created_by.email,
            text="text"
        )
        self.assertEqual(content_base_text_create.text, "text")
