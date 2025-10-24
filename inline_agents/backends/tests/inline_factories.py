import factory

from uuid import uuid4

from nexus.inline_agents.models import (
    Agent,
    Version,
    IntegratedAgent,
    Guardrail,
)

from nexus.inline_agents.backends.bedrock.models import Supervisor

from nexus.usecases.projects.tests.project_factory import ProjectFactory


class AgentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Agent

    uuid = uuid4()
    name = factory.Sequence(lambda n: 'test%d' % n)
    slug = factory.Sequence(lambda n: 'test%d' % n)
    instruction = "Be helpful and friendly"
    collaboration_instructions = "send to this agent if user is talking about the topic of the agent"
    foundation_model = "nova-pro"
    is_official = factory.Faker('boolean')
    project = factory.SubFactory(ProjectFactory)


class IntegratedAgentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IntegratedAgent

    project = factory.SubFactory(ProjectFactory)
    project_uuid = factory.LazyAttribute(lambda integrated_agent: integrated_agent.project.uuid)
    agent = factory.SubFactory(
        AgentFactory,
        project=factory.LazyAttribute(lambda agent: agent.team.project),
    )


class VersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Version

    skills = [{"name": "test_skill", "description": "test description"}]
    display_skills = [{"name": "test_skill", "description": "test description"}]
    agent = factory.SubFactory(
        AgentFactory,
    )


class GuardrailFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Guardrail

    identifier = factory.Sequence(lambda n: 'test%d' % n)
    version = factory.Sequence(lambda n: n)
    changelog = factory.Faker('json')
    current_version = factory.Faker('boolean')


class SupervisorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Supervisor

    name = factory.Sequence(lambda n: 'test%d' % n)
    instruction = factory.Faker('text')
    foundation_model = "nova-pro"
    prompt_override_configuration = {"default": {}, "components": {}}
    action_groups = []
    knowledge_bases = [{"knowledgeBaseId": "test-kb-id"}]
