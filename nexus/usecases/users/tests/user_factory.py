import factory

from nexus.users.models import User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: 'test%d@test.com' % n)
    language = 'en'
