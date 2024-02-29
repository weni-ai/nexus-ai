from django.test import TestCase

from ..models import User


class TestUserManager(TestCase):

    def setUp(self) -> None:
        self.user_email = 'test@test.com'

    def test_create_user(self):
        user = User.objects.create_user(email=self.user_email)
        self.assertEqual(user.email, self.user_email)
        self.assertFalse(user.is_superuser)

    def test_create_super_user(self):
        with self.assertRaises(NotImplementedError):
            User.objects.create_superuser(email=self.user_email)

    def test_create_user_without_email(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email='')
