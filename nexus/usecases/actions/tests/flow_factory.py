from uuid import uuid4

import factory

from nexus.actions.models import Flow, TemplateAction
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFactory


class FlowFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Flow

    flow_uuid = str(uuid4().hex)
    name = factory.Sequence(lambda n: "test%d" % n)
    prompt = factory.Sequence(lambda n: "test%d" % n)
    content_base = factory.SubFactory(
        ContentBaseFactory,
    )
    fallback = False


class TemplateActionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateAction

    uuid = str(uuid4().hex)
    name = factory.Sequence(lambda n: "test%d" % n)
    prompt = factory.Sequence(lambda n: "test%d" % n)
    action_type = "custom"
    group = "test"
    language = "pt-br"
    display_prompt = factory.Sequence(lambda n: "test%d" % n)
