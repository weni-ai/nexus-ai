import random

import factory
from django.conf import settings
from django.utils import timezone

from nexus.inline_agents.models import InlineAgentMessage
from nexus.intelligences.models import (
    LLM,
    ContentBase,
    ContentBaseAgent,
    ContentBaseFile,
    ContentBaseInstruction,
    ContentBaseLink,
    ContentBaseText,
    Conversation,
    IntegratedIntelligence,
    Intelligence,
    SubTopics,
    Topics,
)
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.users.tests.user_factory import UserFactory


class IntelligenceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Intelligence

    name = factory.Sequence(lambda n: "test%d" % n)
    org = factory.SubFactory(OrgFactory, created_by=factory.SelfAttribute("..created_by"))
    created_by = factory.SubFactory(UserFactory)
    description = factory.Sequence(lambda n: "test%d" % n)


class ContentBaseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentBase

    title = factory.Sequence(lambda n: "test%d" % n)
    created_by = factory.SubFactory(UserFactory)
    intelligence = factory.SubFactory(IntelligenceFactory, created_by=factory.SelfAttribute("..created_by"))
    description = factory.Sequence(lambda n: "test%d" % n)
    language = "en"
    is_router = False

    agent = factory.RelatedFactory(
        "nexus.usecases.intelligences.tests.intelligence_factory.ContentBaseAgentFactory", "content_base"
    )
    instruction = factory.RelatedFactory(
        "nexus.usecases.intelligences.tests.intelligence_factory.ContentBaseInstructionFactory", "content_base"
    )


class ContentBaseTextFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentBaseText

    created_by = factory.SubFactory(UserFactory)
    content_base = factory.SubFactory(ContentBaseFactory, created_by=factory.SelfAttribute("..created_by"))
    text = factory.Sequence(lambda n: "test%d" % n)


class ContentBaseFileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentBaseFile

    created_by = factory.SubFactory(UserFactory)
    content_base = factory.SubFactory(ContentBaseFactory, created_by=factory.SelfAttribute("..created_by"))
    file = factory.Sequence(lambda n: "test%d" % n)
    file_name = factory.Sequence(lambda n: "test%d" % n)
    extension_file = "pdf"


class IntegratedIntelligenceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IntegratedIntelligence

    created_by = factory.SubFactory(UserFactory)
    intelligence = factory.SubFactory(
        IntelligenceFactory,
        created_by=factory.SelfAttribute("..created_by"),
    )
    project = factory.SubFactory(
        ProjectFactory,
        name=factory.SelfAttribute("..intelligence.name"),
        created_by=factory.SelfAttribute("..created_by"),
        org=factory.SelfAttribute("..intelligence.org"),
    )


class ContentBaseLinkFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentBaseLink

    created_by = factory.SubFactory(UserFactory)
    content_base = factory.SubFactory(ContentBaseFactory, created_by=factory.SelfAttribute("..created_by"))
    link = factory.Sequence(lambda n: "test%d" % n)


class LLMFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LLM

    model = "gpt2"
    created_by = factory.SubFactory(UserFactory)
    setup = {
        "top_p": settings.WENIGPT_TOP_P,
        "top_k": settings.WENIGPT_TOP_K,
        "temperature": settings.WENIGPT_TEMPERATURE,
        "threshold": 0.5,
        "max_length": 100,
    }

    integrated_intelligence = factory.SubFactory(
        IntegratedIntelligenceFactory, created_by=factory.SelfAttribute("..created_by")
    )


class ContentBaseAgentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentBaseAgent

    content_base = factory.SubFactory(ContentBaseFactory)


class ContentBaseInstructionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentBaseInstruction

    content_base = factory.SubFactory(ContentBaseFactory)
    instruction = factory.Sequence(lambda n: "test%d" % n)


class TopicsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Topics

    name = factory.Sequence(lambda n: "test%d" % n)
    description = factory.Sequence(lambda n: "test%d" % n)
    project = factory.SubFactory(ProjectFactory)


class SubTopicsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubTopics

    name = factory.Sequence(lambda n: "test%d" % n)
    description = factory.Sequence(lambda n: "test%d" % n)
    topic = factory.SubFactory(TopicsFactory)


class InlineAgentMessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InlineAgentMessage

    project = factory.SubFactory(ProjectFactory)
    session_id = factory.Sequence(lambda n: "test%d" % n)
    contact_urn = factory.Sequence(lambda n: "test%d" % n)
    source_type = random.choice(["agent", "user"])
    source = random.choice(["router", "preview"])
    text = factory.Sequence(lambda n: "test%d" % n)


class ConversationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Conversation

    project = factory.SubFactory(ProjectFactory)
    contact_urn = factory.Sequence(lambda n: "test%d" % n)
    start_date = factory.Faker("date_time_between", start_date="-30d", end_date="now", tzinfo=timezone.utc)
    end_date = factory.Faker("date_time_between", start_date="-1d", end_date="now", tzinfo=timezone.utc)
    has_chats_room = factory.Faker("boolean")
    channel_uuid = factory.Faker("uuid4")
    csat = factory.Faker("random_element", elements=[choice[0] for choice in Conversation.CSAT_CHOICES])
    resolution = factory.Faker("random_element", elements=[choice[0] for choice in Conversation.RESOLUTION_CHOICES])
    topic = factory.SubFactory(TopicsFactory)
    subtopic = factory.SubFactory(SubTopicsFactory, topic=factory.SelfAttribute("..topic"))
