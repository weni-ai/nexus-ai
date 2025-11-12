import factory

from nexus.inline_agents.models import InlineAgentMessage
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class InlineAgentMessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InlineAgentMessage

    uuid = factory.Faker("uuid4")
    text = factory.Faker("sentence")
    source_type = "agent"
    source = "content_base_file"
    project = factory.SubFactory(ProjectFactory)
    contact_urn = factory.Faker("phone_number")

    @factory.lazy_attribute
    def session_id(self):
        return f"project-{self.project.uuid}-session-{self.contact_urn}"
