import pytest

from nexus.users.models import User


@pytest.mark.django_db
def test_user_create():
    User.objects.create_user('test@user.com')
    assert User.objects.count() == 1


@pytest.mark.django_db
def test_fail_user_create():
    with pytest.raises(ValueError):
        User.objects.create_user(None)


@pytest.mark.django_db
def test_fail_superuser_create():
    with pytest.raises(NotImplementedError):
        User.objects.create_superuser('test@user.com')
