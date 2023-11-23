from django.test import TestCase

from ..list import ListIntelligencesUseCase, ListContentBaseUseCase
from .intelligence_factory import IntelligenceFactory, ContentBaseFactory
from nexus.usecases.orgs.tests.org_factory import OrgFactory


class TestListIntelligenceUseCase(TestCase):

    def setUp(self):
        self.org = OrgFactory()
        self.intelligence = IntelligenceFactory(org=self.org)

    def test_count_intelligence_use_case(self):
        use_case = ListIntelligencesUseCase()
        intelligences_list = use_case.get_org_intelligences(self.org.uuid)
        self.assertEqual(1, len(intelligences_list))


class TestListContentBaseUseCase(TestCase):

    def setUp(self):

        self.intelligence = IntelligenceFactory()
        self.contentbase = ContentBaseFactory(intelligence=self.intelligence)

    def test_count_contentbase_use_case(self):
        use_case = ListContentBaseUseCase()
        contentbase_list = use_case.get_intelligence_contentbases(
            self.intelligence.uuid
        )
        self.assertEqual(1, len(contentbase_list))
