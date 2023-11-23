from django.test import TestCase
from ..delete import DeleteIntelligenceUseCase, DeleteContentBaseUseCase
from nexus.intelligences.models import Intelligence, ContentBase
from .intelligence_factory import IntelligenceFactory, ContentBaseFactory


class TestDeleteIntelligenceUseCase(TestCase):
    def setUp(self):
        self.use_case = DeleteIntelligenceUseCase()
        self.intelligence = IntelligenceFactory()

    def test_delete_intelligence(self):
        self.use_case.delete_intelligences(self.intelligence.uuid)
        self.assertEqual(Intelligence.objects.count(), 0)


class TestDeleteContentBaseUseCase(TestCase):

    def setUp(self):

        self.contentbase = ContentBaseFactory()

    def test_delete_contentbase(self):
        use_case = DeleteContentBaseUseCase()
        use_case.delete_contentbase(self.contentbase.uuid)
        self.assertEqual(ContentBase.objects.count(), 0)
