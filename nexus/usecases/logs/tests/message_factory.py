import factory
import pendulum

from nexus.logs.models import Message, MessageLog
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class MessageFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = Message

    text = factory.Sequence(lambda n: f'Text {n}')
    contact_urn = 'whatsapp:+1234567890'
    status = 'S'


class MessageLogFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = MessageLog

    message = factory.SubFactory(MessageFactory)
    prompt = 'prompt'
    llm_response = 'response'
    content_base = factory.SubFactory(
        ContentBaseFactory
    )
    project = factory.SubFactory(
        ProjectFactory,
        created_by=factory.SelfAttribute('..content_base.intelligence.created_by')
    )
    created_at = pendulum.now()
