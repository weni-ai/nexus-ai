from uuid import uuid4

import factory

from nexus.projects.models import IntegratedFeature, Project, ProjectAuth, ProjectAuthorizationRole
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.users.tests.user_factory import UserFactory


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    name = factory.Sequence(lambda n: "test%d" % n)
    is_template = False
    template_type = None
    created_by = factory.SubFactory(UserFactory)
    org = factory.SubFactory(OrgFactory, created_by=factory.SelfAttribute("..created_by"))
    brain_on = False
    project_auth = factory.RelatedFactory(
        "nexus.usecases.projects.tests.project_factory.ProjectAuthFactory",
        "project",
        user=factory.SelfAttribute("..created_by"),
        role=ProjectAuthorizationRole.MODERATOR.value,
    )


class ProjectAuthFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProjectAuth

    user = factory.SubFactory(UserFactory)
    project = factory.SubFactory(ProjectFactory)
    role = ProjectAuthorizationRole.MODERATOR.value


class IntegratedFeatureFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IntegratedFeature

    project = factory.SubFactory(ProjectFactory)
    feature_uuid = uuid4().hex
    current_version_setup = [
        {
            "name": "Human handoff",
            "root_flow_uuid": uuid4().hex,
            "prompt": "Whenever an user wants to talk to a human",
            "type": None,
        }
    ]
    is_integrated = False
