import factory

from nexus.orgs.models import Org
from nexus.usecases.users.tests.user_factory import UserFactory


class OrgFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Org

    name = factory.Sequence(lambda n: 'test%d' % n)
    created_by = factory.SubFactory(UserFactory)
