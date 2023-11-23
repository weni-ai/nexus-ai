import factory

from nexus.intelligences.models import Intelligence, ContentBase

from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.users.tests.user_factory import UserFactory


class IntelligenceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Intelligence

    name = factory.Sequence(lambda n: 'test%d' % n)
    org = factory.SubFactory(OrgFactory)
    created_by = factory.SubFactory(UserFactory)
    description = factory.Sequence(lambda n: 'test%d' % n)


class ContentBaseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentBase

    title = factory.Sequence(lambda n: 'test%d' % n)
    intelligence = factory.SubFactory(IntelligenceFactory)
    created_by = factory.SubFactory(UserFactory)
