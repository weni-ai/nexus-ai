import factory

from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText,
    ContentBaseFile,
    IntegratedIntelligence
)

from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.users.tests.user_factory import UserFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory


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
    is_router = False


class ContentBaseTextFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentBaseText

    created_by = factory.SubFactory(UserFactory)
    content_base = factory.SubFactory(
        ContentBaseFactory,
        created_by=factory.SelfAttribute('..created_by')
    )
    text = factory.Sequence(lambda n: 'test%d' % n)


class ContentBaseFileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentBaseFile

    created_by = factory.SubFactory(UserFactory)
    content_base = factory.SubFactory(
        ContentBaseFactory,
        created_by=factory.SelfAttribute('..created_by')
    )
    file = factory.Sequence(lambda n: 'test%d' % n)
    file_name = factory.Sequence(lambda n: 'test%d' % n)
    extension_file = 'pdf'


class IntegratedIntelligenceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IntegratedIntelligence

    intelligence = factory.SubFactory(IntelligenceFactory)
    project = factory.SubFactory(
        ProjectFactory,
        created_by=factory.SelfAttribute('..created_by'),
        org=factory.SelfAttribute('..intelligence.org')
    )
    created_by = factory.SelfAttribute('intelligence.created_by')
