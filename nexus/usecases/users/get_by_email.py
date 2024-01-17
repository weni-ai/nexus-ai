from nexus.users.models import User
from .exceptions import UserDoesNotExists
from django.core.exceptions import ValidationError


def get_by_email(user_email: str) -> User:
    try:
        return User.objects.get(email=user_email)
    except (User.DoesNotExist, ValidationError):
        raise UserDoesNotExists(f"User `{user_email}` does not exists!")
