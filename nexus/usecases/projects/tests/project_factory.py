import factory

from uuid import uuid4
from faker import Faker

from nexus.projects.models import (
    Project,
    ProjectAuth,
    ProjectAuthorizationRole,
    FeatureVersion
)
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.users.tests.user_factory import UserFactory


fake = Faker()

class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    name = factory.Sequence(lambda n: 'test%d' % n)
    is_template = False
    template_type = None
    created_by = factory.SubFactory(UserFactory)
    org = factory.SubFactory(
        OrgFactory,
        created_by=factory.SelfAttribute('..created_by')
    )
    brain_on = False
    project_auth = factory.RelatedFactory(
        'nexus.usecases.projects.tests.project_factory.ProjectAuthFactory',
        'project',
        user=factory.SelfAttribute('..created_by')
    )


class ProjectAuthFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = ProjectAuth

    project = factory.SubFactory(ProjectFactory)
    user = factory.SubFactory(UserFactory)
    role = ProjectAuthorizationRole.MODERATOR.value


class FeatureVersionFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = FeatureVersion

    uuid = uuid4().hex
    setup = {
        "agent": {
            "name": fake.name(),
            "role": fake.job(),
            "personality": fake.word(
                ext_word_list=[
                    "Amigável",
                    "Cooperativo",
                    "Extrovertido",
                    "Generoso"
                ]
            ),
            "goal": "tirar duvidas sobre agentes inteligentes",
        },
        "instructions": [
            "não falar palavrão",
            "não fazer piada"
        ],
        "actions": [
            {
                "name": "atendimento humano",
                "description": "Caso o usuário queira falar com um atendente humano"
            }
        ]
    }
