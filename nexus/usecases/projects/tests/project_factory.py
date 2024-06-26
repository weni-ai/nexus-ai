import factory

from nexus.projects.models import Project, ProjectAuth, ProjectAuthorizationRole
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.users.tests.user_factory import UserFactory


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
