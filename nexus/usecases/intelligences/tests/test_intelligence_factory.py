from django.test import TestCase

from .intelligence_factory import IntelligenceFactory


class TestIntelligenceFactory(TestCase):

    def setUp(self):
        self.intelligence = IntelligenceFactory()

    def test_intelligence_factory(self):
        self.assertEqual(self.intelligence.name, 'test0')
        self.assertEqual(self.intelligence.org.name, 'test0')
        self.assertEqual(self.intelligence.created_by.email, 'test1@test.com')
