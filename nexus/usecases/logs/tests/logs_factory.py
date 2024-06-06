import factory
import pendulum

from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.users.tests.user_factory import UserFactory
from nexus.usecases.intelligences.tests.intelligence_factory import (
    ContentBaseFactory,
    IntelligenceFactory
)
from nexus.logs.models import (
    Message,
    MessageLog,
    RecentActivities
)


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


class RecentActivitiesFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = RecentActivities

    action_model = 'model'
    action_type = 'C'
    created_by = factory.SubFactory(UserFactory)
    project = factory.SubFactory(ProjectFactory)
    intelligence = factory.SubFactory(
        IntelligenceFactory,
        created_by=factory.SelfAttribute('..project.created_by'),
        org=factory.SelfAttribute('..project.org')
    )
    created_at = pendulum.now()
