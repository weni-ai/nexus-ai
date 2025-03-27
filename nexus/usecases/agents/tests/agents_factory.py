import factory

from uuid import uuid4

from nexus.agents.models import (
    Agent,
    AgentSkills,
    AgentVersion,
    AgentSkillVersion,
    Team,
    TeamVersion,
    ActiveAgent
)

from nexus.usecases.users.tests.user_factory import UserFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class AgentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Agent

    created_by = factory.SubFactory(UserFactory)
    project = factory.SubFactory(
        ProjectFactory,
        created_by=factory.SelfAttribute('..created_by')
    )
    uuid = str(uuid4())
    slug = factory.Sequence(lambda n: 'test%d' % n)
    display_name = factory.Sequence(lambda n: 'test%d' % n)
    model = 'gpt-4o-mini'
    is_official = False
    description = 'Agent factory test description'
    external_id = factory.Sequence(lambda n: 'test%d' % n)
    metadata = {}  # fill this


class AgentVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AgentVersion

    created_by = factory.SubFactory(UserFactory)
    agent = factory.SubFactory(
        AgentFactory,
        created_by=factory.SelfAttribute('..created_by')
    )
    alias_id = factory.Sequence(lambda n: 'test%d' % n)
    alias_name = factory.Sequence(lambda n: 'test%d' % n)
    metadata = {}  # fill this


class AgentSkillsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AgentSkills

    display_name = factory.Sequence(lambda n: 'test%d' % n)
    unique_name = factory.Sequence(lambda n: 'test%d' % n)
    created_by = factory.SubFactory(UserFactory)
    agent = factory.SubFactory(
        AgentFactory,
        created_by=factory.SelfAttribute('..created_by')
    )
    skill = {
        'function_schema': [
            {
                'name': 'test',
                'parameters': {
                    'event': {
                        'type': 'string',
                        'required': True,
                        'description': 'Random string with numbers',
                        'contact_field': True
                    },
                    'context': {
                        'type': 'string',
                        'required': True,
                        'description': 'Random string',
                        'contact_field': False
                    }
                }
            }
        ]
    }  # fill this


class AgentSkillVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AgentSkillVersion

    created_by = factory.SubFactory(UserFactory)
    agent_skill = factory.SubFactory(
        AgentSkillsFactory,
        created_by=factory.SelfAttribute('..created_by')
    )
    version = 1
    metadata = {}  # fill this


class TeamFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Team

    external_id = factory.Sequence(lambda n: 'test%d' % n)
    project = factory.SubFactory(ProjectFactory)
    metadata = {}  # fill this

    @factory.post_generation
    def create_supervisor_agent(self, create, extracted, **kwargs):
        if not create:
            return

        AgentFactory(
            external_id=self.external_id,
        )


class TeamVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TeamVersion

    created_by = factory.SubFactory(UserFactory)
    team = factory.SubFactory(TeamFactory)
    alias_id = factory.Sequence(lambda n: 'test%d' % n)
    alias_name = factory.Sequence(lambda n: 'test%d' % n)
    metadata = {}  # fill this


class ActiveAgentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ActiveAgent

    created_by = factory.SubFactory(UserFactory)
    agent = factory.SubFactory(
        AgentFactory,
        created_by=factory.SelfAttribute('..created_by')
    )
    team = factory.SubFactory(
        TeamFactory,
        project=factory.SelfAttribute('..agent.project')
    )
    is_official = False
    metadata = {}  # fill this
