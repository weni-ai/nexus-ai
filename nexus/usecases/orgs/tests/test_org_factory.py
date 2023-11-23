from django.test import TestCase

from .org_factory import OrgFactory


class TestOrgFactory(TestCase):

    def setUp(self):
        self.org = OrgFactory()

    def test_org_factory(self):
        self.assertEqual(self.org.name, 'test0')
        self.assertEqual(self.org.created_by.email, 'test0@test.com')
