from django.test import TestCase

from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText
)
from ..retrieve import (
    RetrieveContentBaseTextUseCase,
    RetrieveContentBaseUseCase,
    RetrieveIntelligenceUseCase
)
from .intelligence_factory import (
    IntelligenceFactory,
    ContentBaseFactory,
    ContentBaseTextFactory
)


class TestRetrieveIntelligenceUseCase(TestCase):

    def setUp(self):
        self.intelligence = IntelligenceFactory()

    def test_count_intelligence_use_case(self):
        use_case = RetrieveIntelligenceUseCase()
        intelligences_retrieve = use_case.get_intelligence(
            intelligence_uuid=self.intelligence.uuid,
            user_email=self.intelligence.created_by.email
        )
        self.assertIsNotNone(intelligences_retrieve)
        self.assertIsInstance(intelligences_retrieve, Intelligence)


class TestRetrieveContentBaseUseCase(TestCase):

    def setUp(self):
        self.contentbase = ContentBaseFactory()

    def test_count_contentbase_use_case(self):
        use_case = RetrieveContentBaseUseCase()
        contentbase_retrieve = use_case.get_contentbase(
            contentbase_uuid=self.contentbase.uuid,
            user_email=self.contentbase.created_by.email
        )
        self.assertIsNotNone(contentbase_retrieve)
        self.assertIsInstance(contentbase_retrieve, ContentBase)


class TestRetrieveContentBaseTextUseCase(TestCase):

    def setUp(self):
        self.contentbasetext = ContentBaseTextFactory()

    def test_count_contentbasetext_use_case(self):
        use_case = RetrieveContentBaseTextUseCase()
        contentbasetext_retrieve = use_case.get_contentbasetext(
            contentbasetext_uuid=self.contentbasetext.uuid,
            user_email=self.contentbasetext.created_by.email
        )
        self.assertIsNotNone(contentbasetext_retrieve)
        self.assertIsInstance(contentbasetext_retrieve, ContentBaseText)
