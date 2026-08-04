from nexus.users.models import User


class CreateUserUseCase:
    def get_or_create_user(self, email: str) -> User:
        user, _ = User.objects.get_or_create(email=email)
        return user
