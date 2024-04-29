import factory

from nexus.intelligences.models import (
    Intelligence,
    ContentBase,
    ContentBaseText,
    ContentBaseFile,
    IntegratedIntelligence,
    ContentBaseLink,
    LLM,
    ContentBaseAgent,
    ContentBaseInstruction,
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
    created_by = factory.SubFactory(UserFactory)
    intelligence = factory.SubFactory(
        IntelligenceFactory,
        created_by=factory.SelfAttribute('..created_by')
    )
    description = factory.Sequence(lambda n: 'test%d' % n)
    language = 'en'
    is_router = False

    agent = factory.RelatedFactory(
        "nexus.usecases.intelligences.tests.intelligence_factory.ContentBaseAgentFactory",
        'content_base'
    )
    instruction = factory.RelatedFactory(
        "nexus.usecases.intelligences.tests.intelligence_factory.ContentBaseInstructionFactory",
        'content_base'
    )


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

    created_by = factory.SubFactory(UserFactory)
    intelligence = factory.SubFactory(
        IntelligenceFactory,
        created_by=factory.SelfAttribute('..created_by'),
    )
    project = factory.SubFactory(
        ProjectFactory,
        created_by=factory.SelfAttribute('..created_by'),
        org=factory.SelfAttribute('..intelligence.org')
    )


class ContentBaseLinkFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentBaseLink

    created_by = factory.SubFactory(UserFactory)
    content_base = factory.SubFactory(
        ContentBaseFactory,
        created_by=factory.SelfAttribute('..created_by')
    )
    link = factory.Sequence(lambda n: 'test%d' % n)


class LLMFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LLM

    model = 'gpt2'
    created_by = factory.SubFactory(UserFactory)
    setup = {
        'top_p': 0.9,
        'top_k': 0.9,
        'temperature': 0.5,
        'threshold': 0.5,
        'max_length': 100
    }

    integrated_intelligence = factory.SubFactory(
        IntegratedIntelligenceFactory,
        created_by=factory.SelfAttribute('..created_by')
    )


class ContentBaseAgentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentBaseAgent

    content_base = factory.SubFactory(ContentBaseFactory)


class ContentBaseInstructionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentBaseInstruction

    content_base = factory.SubFactory(ContentBaseFactory)
    instruction = factory.Sequence(lambda n: 'test%d' % n)
