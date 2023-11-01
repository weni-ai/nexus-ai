from pytest import fixture

from nexus.users.models import User


@fixture
def create_user():
    return User.objects.create_user('test@user.com')
