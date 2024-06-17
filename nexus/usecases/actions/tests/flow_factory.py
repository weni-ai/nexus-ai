import factory

from uuid import uuid4

from nexus.actions.models import Flow
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFactory


class FlowFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = Flow

    uuid = str(uuid4().hex)
    name = factory.Sequence(lambda n: 'test%d' % n)
    prompt = factory.Sequence(lambda n: 'test%d' % n)
    content_base = factory.SubFactory(
        ContentBaseFactory,
    )
    fallback = False
