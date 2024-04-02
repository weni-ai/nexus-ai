import factory

from uuid import uuid4

from nexus.actions.models import Flow
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFactory
from nexus.usecases.users.tests.user_factory import UserFactory


class FlowFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = Flow

    uuid = str(uuid4().hex)
    name = factory.Sequence(lambda n: 'test%d' % n)
    prompt = factory.Sequence(lambda n: 'test%d' % n)
    created_by = factory.SubFactory(UserFactory)
    content_base = factory.SubFactory(
        ContentBaseFactory,
        created_by=factory.SelfAttribute('..created_by')
    )
    fallback = False
