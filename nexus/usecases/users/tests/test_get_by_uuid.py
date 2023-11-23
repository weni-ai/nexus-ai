from django.test import TestCase

from ..get_by_email import get_by_email
from ..exceptions import UserDoesNotExists
from .user_factory import UserFactory


class TestGetByEmailTestCase(TestCase):

    def setUp(self):
        self.user = UserFactory()

    def test_get_by_email(self):
        retrieved_user = get_by_email(self.user.email)
        self.assertEqual(self.user, retrieved_user)

    def test_get_by_email_nonexistent(self):
        with self.assertRaises(UserDoesNotExists):
            get_by_email("nonexistent_email")

    def test_get_by_email_invalid(self):
        with self.assertRaises(UserDoesNotExists):
            get_by_email("invalid_email")

    def test_get_by_email_none(self):
        with self.assertRaises(UserDoesNotExists):
            get_by_email(None)
