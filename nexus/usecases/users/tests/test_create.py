from django.test import TestCase

from nexus.users.models import User

from ..create import CreateUserUseCase


class TestCreateUserUseCase(TestCase):
    def setUp(self):
        self.usecase = CreateUserUseCase()
        self.user_email = "test@create.com"

    def test_get_or_create_user(self):
        user = self.usecase.get_or_create_user(self.user_email)
        self.assertEqual(user.email, self.user_email)
        self.assertIsInstance(user, User)
