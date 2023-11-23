import factory

from nexus.users.models import User


class UserFactory(factory.Factory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: 'test%d@test.com' % n)
    language = 'en'
