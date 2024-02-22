import factory

from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText
)

from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.users.tests.user_factory import UserFactory


class IntelligenceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Intelligence

    name = factory.Sequence(lambda n: 'test%d' % n)
    org = factory.SubFactory(
        OrgFactory,
        created_by=factory.SelfAttribute('..created_by')
    )
    created_by = factory.SubFactory(UserFactory)
    description = factory.Sequence(lambda n: 'test%d' % n)


class ContentBaseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentBase

    title = factory.Sequence(lambda n: 'test%d' % n)
    intelligence = factory.SubFactory(
        IntelligenceFactory,
        created_by=factory.SelfAttribute('..created_by')
    )
    created_by = factory.SubFactory(UserFactory)
    description = factory.Sequence(lambda n: 'test%d' % n)
    language = 'en'


class ContentBaseTextFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentBaseText

    created_by = factory.SubFactory(UserFactory)
    content_base = factory.SubFactory(
        ContentBaseFactory,
        created_by=factory.SelfAttribute('..created_by')
    )
    text = factory.Sequence(lambda n: 'test%d' % n)
