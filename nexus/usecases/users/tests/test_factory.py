from django.test import TestCase

from .user_factory import UserFactory


class TestUserFactory(TestCase):

    def setUp(self):
        self.user = UserFactory()

    def test_user_factory(self):
        self.assertEqual(self.user.email, 'test0@test.com')
