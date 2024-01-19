from django.test import TestCase

from ..create import CreateUserUseCase
from nexus.users.models import User


class TestCreateUserUseCase(TestCase):

    def setUp(self):
        self.usecase = CreateUserUseCase()
        self.user_email = "test@create.com"

    def test_get_by_email(self):
        user = self.usecase.create_user(self.user_email)
        self.assertEqual(user.email, self.user_email)
        self.assertIsInstance(user, User)
